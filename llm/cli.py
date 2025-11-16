import asyncio
import click
from click_default_group import DefaultGroup
from dataclasses import asdict
import io
import json
import os
from llm import (
    Attachment,
    AsyncConversation,
    AsyncKeyModel,
    AsyncResponse,
    CancelToolCall,
    Collection,
    Conversation,
    Fragment,
    Response,
    Template,
    Tool,
    Toolbox,
    UnknownModelError,
    KeyModel,
    encode,
    get_async_model,
    get_default_model,
    get_default_embedding_model,
    get_embedding_models_with_aliases,
    get_embedding_model_aliases,
    get_embedding_model,
    get_plugins,
    get_tools,
    get_fragment_loaders,
    get_template_loaders,
    get_model,
    get_model_aliases,
    get_models_with_aliases,
    user_dir,
    set_alias,
    set_default_model,
    set_default_embedding_model,
    remove_alias,
)
from llm.models import _BaseConversation, ChainResponse

from .migrations import migrate
from .plugins import pm, load_plugins
from .utils import (
    ensure_fragment,
    extract_fenced_code_block,
    find_unused_key,
    has_plugin_prefix,
    instantiate_from_spec,
    make_schema_id,
    maybe_fenced_code,
    mimetype_from_path,
    mimetype_from_string,
    multi_schema,
    output_rows_as_json,
    resolve_schema_input,
    schema_dsl,
    schema_summary,
    token_usage_string,
    truncate_string,
)
import base64
import httpx
import inspect
import pathlib
import pydantic
import re
import readline
from runpy import run_module
import shutil
import sqlite_utils
from sqlite_utils.utils import rows_from_file, Format
import sys
import textwrap
from typing import cast, Dict, Optional, Iterable, List, Union, Tuple, Type, Any
import warnings
import yaml

warnings.simplefilter("ignore", ResourceWarning)

DEFAULT_TEMPLATE = "prompt: "


class FragmentNotFound(Exception):
    pass


def validate_fragment_alias(ctx, param, value):
    if not re.match(r"^[a-zA-Z0-9_-]+$", value):
        raise click.BadParameter("Fragment alias must be alphanumeric")
    return value


def resolve_fragments(
    db: sqlite_utils.Database, fragments: Iterable[str], allow_attachments: bool = False
) -> List[Union[Fragment, Attachment]]:
    """
    Resolve fragment strings into a mixed of llm.Fragment() and llm.Attachment() objects.
    """

    def _load_by_alias(fragment: str) -> Tuple[Optional[str], Optional[str]]:
        rows = list(
            db.query(
                """
                select content, source from fragments
                left join fragment_aliases on fragments.id = fragment_aliases.fragment_id
                where alias = :alias or hash = :alias limit 1
                """,
                {"alias": fragment},
            )
        )
        if rows:
            row = rows[0]
            return row["content"], row["source"]
        return None, None

    # The fragment strings could be URLs or paths or plugin references
    resolved: List[Union[Fragment, Attachment]] = []
    for fragment in fragments:
        if fragment.startswith("http://") or fragment.startswith("https://"):
            client = httpx.Client(follow_redirects=True, max_redirects=3)
            response = client.get(fragment)
            response.raise_for_status()
            resolved.append(Fragment(response.text, fragment))
        elif fragment == "-":
            resolved.append(Fragment(sys.stdin.read(), "-"))
        elif has_plugin_prefix(fragment):
            prefix, rest = fragment.split(":", 1)
            loaders = get_fragment_loaders()
            if prefix not in loaders:
                raise FragmentNotFound("Unknown fragment prefix: {}".format(prefix))
            loader = loaders[prefix]
            try:
                result = loader(rest)
                if not isinstance(result, list):
                    result = [result]
                if not allow_attachments and any(
                    isinstance(r, Attachment) for r in result
                ):
                    raise FragmentNotFound(
                        "Fragment loader {} returned a disallowed attachment".format(
                            prefix
                        )
                    )
                resolved.extend(result)
            except Exception as ex:
                raise FragmentNotFound(
                    "Could not load fragment {}: {}".format(fragment, ex)
                )
        else:
            # Try from the DB
            content, source = _load_by_alias(fragment)
            if content is not None:
                resolved.append(Fragment(content, source))
            else:
                # Now try path
                path = pathlib.Path(fragment)
                if path.exists():
                    resolved.append(Fragment(path.read_text(), str(path.resolve())))
                else:
                    raise FragmentNotFound(f"Fragment '{fragment}' not found")
    return resolved


def process_fragments_in_chat(
    db: sqlite_utils.Database, prompt: str
) -> tuple[str, list[Fragment], list[Attachment]]:
    """
    Process any !fragment commands in a chat prompt and return the modified prompt plus resolved fragments and attachments.
    """
    prompt_lines = []
    fragments = []
    attachments = []
    for line in prompt.splitlines():
        if line.startswith("!fragment "):
            try:
                fragment_strs = line.strip().removeprefix("!fragment ").split()
                fragments_and_attachments = resolve_fragments(
                    db, fragments=fragment_strs, allow_attachments=True
                )
                fragments += [
                    fragment
                    for fragment in fragments_and_attachments
                    if isinstance(fragment, Fragment)
                ]
                attachments += [
                    attachment
                    for attachment in fragments_and_attachments
                    if isinstance(attachment, Attachment)
                ]
            except FragmentNotFound as ex:
                raise click.ClickException(str(ex))
        else:
            prompt_lines.append(line)
    return "\n".join(prompt_lines), fragments, attachments


class AttachmentError(Exception):
    """Exception raised for errors in attachment resolution."""

    pass


def resolve_attachment(value):
    """
    Resolve an attachment from a string value which could be:
    - "-" for stdin
    - A URL
    - A file path

    Returns an Attachment object.
    Raises AttachmentError if the attachment cannot be resolved.
    """
    if value == "-":
        content = sys.stdin.buffer.read()
        # Try to guess type
        mimetype = mimetype_from_string(content)
        if mimetype is None:
            raise AttachmentError("Could not determine mimetype of stdin")
        return Attachment(type=mimetype, path=None, url=None, content=content)

    if "://" in value:
        # Confirm URL exists and try to guess type
        try:
            response = httpx.head(value)
            response.raise_for_status()
            mimetype = response.headers.get("content-type")
        except httpx.HTTPError as ex:
            raise AttachmentError(str(ex))
        return Attachment(type=mimetype, path=None, url=value, content=None)

    # Check that the file exists
    path = pathlib.Path(value)
    if not path.exists():
        raise AttachmentError(f"File {value} does not exist")
    path = path.resolve()

    # Try to guess type
    mimetype = mimetype_from_path(str(path))
    if mimetype is None:
        raise AttachmentError(f"Could not determine mimetype of {value}")

    return Attachment(type=mimetype, path=str(path), url=None, content=None)


class AttachmentType(click.ParamType):
    name = "attachment"

    def convert(self, value, param, ctx):
        try:
            return resolve_attachment(value)
        except AttachmentError as e:
            self.fail(str(e), param, ctx)


def resolve_attachment_with_type(value: str, mimetype: str) -> Attachment:
    if "://" in value:
        attachment = Attachment(mimetype, None, value, None)
    elif value == "-":
        content = sys.stdin.buffer.read()
        attachment = Attachment(mimetype, None, None, content)
    else:
        # Look for file
        path = pathlib.Path(value)
        if not path.exists():
            raise click.BadParameter(f"File {value} does not exist")
        path = path.resolve()
        attachment = Attachment(mimetype, str(path), None, None)
    return attachment


def attachment_types_callback(ctx, param, values) -> List[Attachment]:
    collected = []
    for value, mimetype in values:
        collected.append(resolve_attachment_with_type(value, mimetype))
    return collected


def json_validator(object_name):
    def validator(ctx, param, value):
        if value is None:
            return value
        try:
            obj = json.loads(value)
            if not isinstance(obj, dict):
                raise click.BadParameter(f"{object_name} must be a JSON object")
            return obj
        except json.JSONDecodeError:
            raise click.BadParameter(f"{object_name} must be valid JSON")

    return validator


def schema_option(fn):
    click.option(
        "schema_input",
        "--schema",
        help="JSON schema, filepath or ID",
    )(fn)
    return fn


@click.group(
    cls=DefaultGroup,
    default="prompt",
    default_if_no_args=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option()
def cli():
    """
    Access Large Language Models from the command-line

    Documentation: https://llm.datasette.io/

    LLM can run models from many different providers. Consult the
    plugin directory for a list of available models:

    https://llm.datasette.io/en/stable/plugins/directory.html

    To get started with OpenAI, obtain an API key from them and:

    \b
        $ llm keys set openai
        Enter key: ...

    Then execute a prompt like this:

        llm 'Five outrageous names for a pet pelican'

    For a full list of prompting options run:

        llm prompt --help
    """


@cli.command(name="prompt")
@click.argument("prompt", required=False)
@click.option("-s", "--system", help="System prompt to use")
@click.option("model_id", "-m", "--model", help="Model to use", envvar="LLM_MODEL")
@click.option(
    "-d",
    "--database",
    type=click.Path(readable=True, dir_okay=False),
    help="Path to log database",
)
@click.option(
    "queries",
    "-q",
    "--query",
    multiple=True,
    help="Use first model matching these strings",
)
@click.option(
    "attachments",
    "-a",
    "--attachment",
    type=AttachmentType(),
    multiple=True,
    help="Attachment path or URL or -",
)
@click.option(
    "attachment_types",
    "--at",
    "--attachment-type",
    type=(str, str),
    multiple=True,
    callback=attachment_types_callback,
    help="\b\nAttachment with explicit mimetype,\n--at image.jpg image/jpeg",
)
@click.option(
    "tools",
    "-T",
    "--tool",
    multiple=True,
    help="Name of a tool to make available to the model",
)
@click.option(
    "python_tools",
    "--functions",
    help="Python code block or file path defining functions to register as tools",
    multiple=True,
)
@click.option(
    "tools_debug",
    "--td",
    "--tools-debug",
    is_flag=True,
    help="Show full details of tool executions",
    envvar="LLM_TOOLS_DEBUG",
)
@click.option(
    "tools_approve",
    "--ta",
    "--tools-approve",
    is_flag=True,
    help="Manually approve every tool execution",
)
@click.option(
    "chain_limit",
    "--cl",
    "--chain-limit",
    type=int,
    default=5,
    help="How many chained tool responses to allow, default 5, set 0 for unlimited",
)
@click.option(
    "options",
    "-o",
    "--option",
    type=(str, str),
    multiple=True,
    help="key/value options for the model",
)
@schema_option
@click.option(
    "--schema-multi",
    help="JSON schema to use for multiple results",
)
@click.option(
    "fragments",
    "-f",
    "--fragment",
    multiple=True,
    help="Fragment (alias, URL, hash or file path) to add to the prompt",
)
@click.option(
    "system_fragments",
    "--sf",
    "--system-fragment",
    multiple=True,
    help="Fragment to add to system prompt",
)
@click.option("-t", "--template", help="Template to use")
@click.option(
    "-p",
    "--param",
    multiple=True,
    type=(str, str),
    help="Parameters for template",
)
@click.option("--no-stream", is_flag=True, help="Do not stream output")
@click.option("-n", "--no-log", is_flag=True, help="Don't log to database")
@click.option("--log", is_flag=True, help="Log prompt and response to the database")
@click.option(
    "_continue",
    "-c",
    "--continue",
    is_flag=True,
    flag_value=-1,
    help="Continue the most recent conversation.",
)
@click.option(
    "conversation_id",
    "--cid",
    "--conversation",
    help="Continue the conversation with the given ID.",
)
@click.option("--key", help="API key to use")
@click.option("--save", help="Save prompt with this template name")
@click.option("async_", "--async", is_flag=True, help="Run prompt asynchronously")
@click.option("-u", "--usage", is_flag=True, help="Show token usage")
@click.option("-x", "--extract", is_flag=True, help="Extract first fenced code block")
@click.option(
    "extract_last",
    "--xl",
    "--extract-last",
    is_flag=True,
    help="Extract last fenced code block",
)
def prompt(
    prompt,
    system,
    model_id,
    database,
    queries,
    attachments,
    attachment_types,
    tools,
    python_tools,
    tools_debug,
    tools_approve,
    chain_limit,
    options,
    schema_input,
    schema_multi,
    fragments,
    system_fragments,
    template,
    param,
    no_stream,
    no_log,
    log,
    _continue,
    conversation_id,
    key,
    save,
    async_,
    usage,
    extract,
    extract_last,
):
    """
    Execute a prompt

    Documentation: https://llm.datasette.io/en/stable/usage.html

    Examples:

    \b
        llm 'Capital of France?'
        llm 'Capital of France?' -m gpt-4o
        llm 'Capital of France?' -s 'answer in Spanish'

    Multi-modal models can be called with attachments like this:

    \b
        llm 'Extract text from this image' -a image.jpg
        llm 'Describe' -a https://static.simonwillison.net/static/2024/pelicans.jpg
        cat image | llm 'describe image' -a -
        # With an explicit mimetype:
        cat image | llm 'describe image' --at - image/jpeg

    The -x/--extract option returns just the content of the first ``` fenced code
    block, if one is present. If none are present it returns the full response.

    \b
        llm 'JavaScript function for reversing a string' -x
    """
    if log and no_log:
        raise click.ClickException("--log and --no-log are mutually exclusive")

    log_path = pathlib.Path(database) if database else logs_db_path()
    (log_path.parent).mkdir(parents=True, exist_ok=True)
    db = sqlite_utils.Database(log_path)
    migrate(db)

    if queries and not model_id:
        # Use -q options to find model with shortest model_id
        matches = []
        for model_with_aliases in get_models_with_aliases():
            if all(model_with_aliases.matches(q) for q in queries):
                matches.append(model_with_aliases.model.model_id)
        if not matches:
            raise click.ClickException(
                "No model found matching queries {}".format(", ".join(queries))
            )
        model_id = min(matches, key=len)

    if schema_multi:
        schema_input = schema_multi

    schema = resolve_schema_input(db, schema_input, load_template)

    if schema_multi:
        # Convert that schema into multiple "items" of the same schema
        schema = multi_schema(schema)

    model_aliases = get_model_aliases()

    def read_prompt():
        nonlocal prompt, schema

        # Is there extra prompt available on stdin?
        stdin_prompt = None
        if not sys.stdin.isatty():
            stdin_prompt = sys.stdin.read()

        if stdin_prompt:
            bits = [stdin_prompt]
            if prompt:
                bits.append(prompt)
            prompt = " ".join(bits)

        if (
            prompt is None
            and not save
            and sys.stdin.isatty()
            and not attachments
            and not attachment_types
            and not schema
            and not fragments
        ):
            # Hang waiting for input to stdin (unless --save)
            prompt = sys.stdin.read()
        return prompt

    if save:
        # We are saving their prompt/system/etc to a new template
        # Fields to save: prompt, system, model - and more in the future
        disallowed_options = []
        for option, var in (
            ("--template", template),
            ("--continue", _continue),
            ("--cid", conversation_id),
        ):
            if var:
                disallowed_options.append(option)
        if disallowed_options:
            raise click.ClickException(
                "--save cannot be used with {}".format(", ".join(disallowed_options))
            )
        path = template_dir() / f"{save}.yaml"
        to_save = {}
        if model_id:
            try:
                to_save["model"] = model_aliases[model_id].model_id
            except KeyError:
                raise click.ClickException("'{}' is not a known model".format(model_id))
        prompt = read_prompt()
        if prompt:
            to_save["prompt"] = prompt
        if system:
            to_save["system"] = system
        if param:
            to_save["defaults"] = dict(param)
        if extract:
            to_save["extract"] = True
        if extract_last:
            to_save["extract_last"] = True
        if schema:
            to_save["schema_object"] = schema
        if fragments:
            to_save["fragments"] = list(fragments)
        if system_fragments:
            to_save["system_fragments"] = list(system_fragments)
        if python_tools:
            to_save["functions"] = "\n\n".join(python_tools)
        if tools:
            to_save["tools"] = list(tools)
        if attachments:
            # Only works for attachments with a path or url
            to_save["attachments"] = [
                (a.path or a.url) for a in attachments if (a.path or a.url)
            ]
        if attachment_types:
            to_save["attachment_types"] = [
                {"type": a.type, "value": a.path or a.url}
                for a in attachment_types
                if (a.path or a.url)
            ]
        if options:
            # Need to validate and convert their types first
            model = get_model(model_id or get_default_model())
            try:
                options_model = model.Options(**dict(options))
                # Use model_dump(mode="json") so Enums become their .value strings
                to_save["options"] = {
                    k: v
                    for k, v in options_model.model_dump(mode="json").items()
                    if v is not None
                }
            except pydantic.ValidationError as ex:
                raise click.ClickException(render_errors(ex.errors()))
        path.write_text(
            yaml.safe_dump(
                to_save,
                indent=4,
                default_flow_style=False,
                sort_keys=False,
            ),
            "utf-8",
        )
        return

    if template:
        params = dict(param)
        # Cannot be used with system
        try:
            template_obj = load_template(template)
        except LoadTemplateError as ex:
            raise click.ClickException(str(ex))
        extract = template_obj.extract
        extract_last = template_obj.extract_last
        # Combine with template fragments/system_fragments
        if template_obj.fragments:
            fragments = [*template_obj.fragments, *fragments]
        if template_obj.system_fragments:
            system_fragments = [*template_obj.system_fragments, *system_fragments]
        if template_obj.schema_object:
            schema = template_obj.schema_object
        if template_obj.tools:
            tools = [*template_obj.tools, *tools]
        if template_obj.functions and template_obj._functions_is_trusted:
            python_tools = [template_obj.functions, *python_tools]
        input_ = ""
        if template_obj.options:
            # Make options mutable (they start as a tuple)
            options = list(options)
            # Load any options, provided they were not set using -o already
            specified_options = dict(options)
            for option_name, option_value in template_obj.options.items():
                if option_name not in specified_options:
                    options.append((option_name, option_value))
        if "input" in template_obj.vars():
            input_ = read_prompt()
        try:
            template_prompt, template_system = template_obj.evaluate(input_, params)
            if template_prompt:
                # Combine with user prompt
                if prompt and "input" not in template_obj.vars():
                    prompt = template_prompt + "\n" + prompt
                else:
                    prompt = template_prompt
            if template_system and not system:
                system = template_system
        except Template.MissingVariables as ex:
            raise click.ClickException(str(ex))
        if model_id is None and template_obj.model:
            model_id = template_obj.model
        # Merge in any attachments
        if template_obj.attachments:
            attachments = [
                resolve_attachment(a) for a in template_obj.attachments
            ] + list(attachments)
        if template_obj.attachment_types:
            attachment_types = [
                resolve_attachment_with_type(at.value, at.type)
                for at in template_obj.attachment_types
            ] + list(attachment_types)
    if extract or extract_last:
        no_stream = True

    conversation = None
    if conversation_id or _continue:
        # Load the conversation - loads most recent if no ID provided
        try:
            conversation = load_conversation(
                conversation_id, async_=async_, database=database
            )
        except UnknownModelError as ex:
            raise click.ClickException(str(ex))

    if conversation_tools := _get_conversation_tools(conversation, tools):
        tools = conversation_tools

    # Figure out which model we are using
    if model_id is None:
        if conversation:
            model_id = conversation.model.model_id
        else:
            model_id = get_default_model()

    # Now resolve the model
    try:
        if async_:
            model = get_async_model(model_id)
        else:
            model = get_model(model_id)
    except UnknownModelError as ex:
        raise click.ClickException(ex)

    if conversation is None and (tools or python_tools):
        conversation = model.conversation()

    if conversation:
        # To ensure it can see the key
        conversation.model = model

    # Validate options
    validated_options = {}
    if options:
        # Validate with pydantic
        try:
            validated_options = dict(
                (key, value)
                for key, value in model.Options(**dict(options))
                if value is not None
            )
        except pydantic.ValidationError as ex:
            raise click.ClickException(render_errors(ex.errors()))

    # Add on any default model options
    default_options = get_model_options(model.model_id)
    for key_, value in default_options.items():
        if key_ not in validated_options:
            validated_options[key_] = value

    kwargs = {}

    resolved_attachments = [*attachments, *attachment_types]

    should_stream = model.can_stream and not no_stream
    if not should_stream:
        kwargs["stream"] = False

    if isinstance(model, (KeyModel, AsyncKeyModel)):
        kwargs["key"] = key

    prompt = read_prompt()
    response = None

    try:
        fragments_and_attachments = resolve_fragments(
            db, fragments, allow_attachments=True
        )
        resolved_fragments = [
            fragment
            for fragment in fragments_and_attachments
            if isinstance(fragment, Fragment)
        ]
        resolved_attachments.extend(
            attachment
            for attachment in fragments_and_attachments
            if isinstance(attachment, Attachment)
        )
        resolved_system_fragments = resolve_fragments(db, system_fragments)
    except FragmentNotFound as ex:
        raise click.ClickException(str(ex))

    prompt_method = model.prompt
    if conversation:
        prompt_method = conversation.prompt

    tool_implementations = _gather_tools(tools, python_tools)

    if tool_implementations:
        prompt_method = conversation.chain
        kwargs["options"] = validated_options
        kwargs["chain_limit"] = chain_limit
        if tools_debug:
            kwargs["after_call"] = _debug_tool_call
        if tools_approve:
            kwargs["before_call"] = _approve_tool_call
        kwargs["tools"] = tool_implementations
    else:
        # Merge in options for the .prompt() methods
        kwargs.update(validated_options)

    try:
        if async_:

            async def inner():
                if should_stream:
                    response = prompt_method(
                        prompt,
                        attachments=resolved_attachments,
                        system=system,
                        schema=schema,
                        fragments=resolved_fragments,
                        system_fragments=resolved_system_fragments,
                        **kwargs,
                    )
                    async for chunk in response:
                        print(chunk, end="")
                        sys.stdout.flush()
                    print("")
                else:
                    response = prompt_method(
                        prompt,
                        fragments=resolved_fragments,
                        attachments=resolved_attachments,
                        schema=schema,
                        system=system,
                        system_fragments=resolved_system_fragments,
                        **kwargs,
                    )
                    text = await response.text()
                    if extract or extract_last:
                        text = (
                            extract_fenced_code_block(text, last=extract_last) or text
                        )
                    print(text)
                return response

            response = asyncio.run(inner())
        else:
            response = prompt_method(
                prompt,
                fragments=resolved_fragments,
                attachments=resolved_attachments,
                system=system,
                schema=schema,
                system_fragments=resolved_system_fragments,
                **kwargs,
            )
            if should_stream:
                for chunk in response:
                    print(chunk, end="")
                    sys.stdout.flush()
                print("")
            else:
                text = response.text()
                if extract or extract_last:
                    text = extract_fenced_code_block(text, last=extract_last) or text
                print(text)
    # List of exceptions that should never be raised in pytest:
    except (ValueError, NotImplementedError) as ex:
        raise click.ClickException(str(ex))
    except Exception as ex:
        # All other exceptions should raise in pytest, show to user otherwise
        if getattr(sys, "_called_from_test", False) or os.environ.get(
            "LLM_RAISE_ERRORS", None
        ):
            raise
        raise click.ClickException(str(ex))

    if usage:
        if isinstance(response, ChainResponse):
            responses = response._responses
        else:
            responses = [response]
        for response_object in responses:
            # Show token usage to stderr in yellow
            click.echo(
                click.style(
                    "Token usage: {}".format(response_object.token_usage()),
                    fg="yellow",
                    bold=True,
                ),
                err=True,
            )

    # Log responses to the database
    if (logs_on() or log) and not no_log:
        # Could be Response, AsyncResponse, ChainResponse, AsyncChainResponse
        if isinstance(response, AsyncResponse):
            response = asyncio.run(response.to_sync_response())
        # At this point ALL forms should have a log_to_db() method that works:
        response.log_to_db(db)


@cli.command()
@click.option("-s", "--system", help="System prompt to use")
@click.option("model_id", "-m", "--model", help="Model to use", envvar="LLM_MODEL")
@click.option(
    "_continue",
    "-c",
    "--continue",
    is_flag=True,
    flag_value=-1,
    help="Continue the most recent conversation.",
)
@click.option(
    "conversation_id",
    "--cid",
    "--conversation",
    help="Continue the conversation with the given ID.",
)
@click.option(
    "fragments",
    "-f",
    "--fragment",
    multiple=True,
    help="Fragment (alias, URL, hash or file path) to add to the prompt",
)
@click.option(
    "system_fragments",
    "--sf",
    "--system-fragment",
    multiple=True,
    help="Fragment to add to system prompt",
)
@click.option("-t", "--template", help="Template to use")
@click.option(
    "-p",
    "--param",
    multiple=True,
    type=(str, str),
    help="Parameters for template",
)
@click.option(
    "options",
    "-o",
    "--option",
    type=(str, str),
    multiple=True,
    help="key/value options for the model",
)
@click.option(
    "-d",
    "--database",
    type=click.Path(readable=True, dir_okay=False),
    help="Path to log database",
)
@click.option("--no-stream", is_flag=True, help="Do not stream output")
@click.option("--key", help="API key to use")
@click.option(
    "tools",
    "-T",
    "--tool",
    multiple=True,
    help="Name of a tool to make available to the model",
)
@click.option(
    "python_tools",
    "--functions",
    help="Python code block or file path defining functions to register as tools",
    multiple=True,
)
@click.option(
    "tools_debug",
    "--td",
    "--tools-debug",
    is_flag=True,
    help="Show full details of tool executions",
    envvar="LLM_TOOLS_DEBUG",
)
@click.option(
    "tools_approve",
    "--ta",
    "--tools-approve",
    is_flag=True,
    help="Manually approve every tool execution",
)
@click.option(
    "chain_limit",
    "--cl",
    "--chain-limit",
    type=int,
    default=5,
    help="How many chained tool responses to allow, default 5, set 0 for unlimited",
)
def chat(
    system,
    model_id,
    _continue,
    conversation_id,
    fragments,
    system_fragments,
    template,
    param,
    options,
    no_stream,
    key,
    database,
    tools,
    python_tools,
    tools_debug,
    tools_approve,
    chain_limit,
):
    """
    Hold an ongoing chat with a model.
    """
    # Left and right arrow keys to move cursor:
    if sys.platform != "win32":
        readline.parse_and_bind("\\e[D: backward-char")
        readline.parse_and_bind("\\e[C: forward-char")
    else:
        readline.parse_and_bind("bind -x '\\e[D: backward-char'")
        readline.parse_and_bind("bind -x '\\e[C: forward-char'")
    log_path = pathlib.Path(database) if database else logs_db_path()
    (log_path.parent).mkdir(parents=True, exist_ok=True)
    db = sqlite_utils.Database(log_path)
    migrate(db)

    conversation = None
    if conversation_id or _continue:
        # Load the conversation - loads most recent if no ID provided
        try:
            conversation = load_conversation(conversation_id, database=database)
        except UnknownModelError as ex:
            raise click.ClickException(str(ex))

    if conversation_tools := _get_conversation_tools(conversation, tools):
        tools = conversation_tools

    template_obj = None
    if template:
        params = dict(param)
        try:
            template_obj = load_template(template)
        except LoadTemplateError as ex:
            raise click.ClickException(str(ex))
        if model_id is None and template_obj.model:
            model_id = template_obj.model
        if template_obj.tools:
            tools = [*template_obj.tools, *tools]
        if template_obj.functions and template_obj._functions_is_trusted:
            python_tools = [template_obj.functions, *python_tools]

    # Figure out which model we are using
    if model_id is None:
        if conversation:
            model_id = conversation.model.model_id
        else:
            model_id = get_default_model()

    # Now resolve the model
    try:
        model = get_model(model_id)
    except KeyError:
        raise click.ClickException("'{}' is not a known model".format(model_id))

    if conversation is None:
        # Start a fresh conversation for this chat
        conversation = Conversation(model=model)
    else:
        # Ensure it can see the API key
        conversation.model = model

    if tools_debug:
        conversation.after_call = _debug_tool_call
    if tools_approve:
        conversation.before_call = _approve_tool_call

    # Validate options
    validated_options = get_model_options(model.model_id)
    if options:
        try:
            validated_options = dict(
                (key, value)
                for key, value in model.Options(**dict(options))
                if value is not None
            )
        except pydantic.ValidationError as ex:
            raise click.ClickException(render_errors(ex.errors()))

    kwargs = {}
    if validated_options:
        kwargs["options"] = validated_options

    tool_functions = _gather_tools(tools, python_tools)

    if tool_functions:
        kwargs["chain_limit"] = chain_limit
        kwargs["tools"] = tool_functions

    should_stream = model.can_stream and not no_stream
    if not should_stream:
        kwargs["stream"] = False

    if key and isinstance(model, KeyModel):
        kwargs["key"] = key

    try:
        fragments_and_attachments = resolve_fragments(
            db, fragments, allow_attachments=True
        )
        argument_fragments = [
            fragment
            for fragment in fragments_and_attachments
            if isinstance(fragment, Fragment)
        ]
        argument_attachments = [
            attachment
            for attachment in fragments_and_attachments
            if isinstance(attachment, Attachment)
        ]
        argument_system_fragments = resolve_fragments(db, system_fragments)
    except FragmentNotFound as ex:
        raise click.ClickException(str(ex))

    click.echo("Chatting with {}".format(model.model_id))
    click.echo("Type 'exit' or 'quit' to exit")
    click.echo("Type '!multi' to enter multiple lines, then '!end' to finish")
    click.echo("Type '!edit' to open your default editor and modify the prompt")
    click.echo(
        "Type '!fragment <my_fragment> [<another_fragment> ...]' to insert one or more fragments"
    )
    in_multi = False

    accumulated = []
    accumulated_fragments = []
    accumulated_attachments = []
    end_token = "!end"
    while True:
        prompt = click.prompt("", prompt_suffix="> " if not in_multi else "")
        fragments = []
        attachments = []
        if argument_fragments:
            fragments += argument_fragments
            # fragments from --fragments will get added to the first message only
            argument_fragments = []
        if argument_attachments:
            attachments = argument_attachments
            argument_attachments = []
        if prompt.strip().startswith("!multi"):
            in_multi = True
            bits = prompt.strip().split()
            if len(bits) > 1:
                end_token = "!end {}".format(" ".join(bits[1:]))
            continue
        if prompt.strip() == "!edit":
            edited_prompt = click.edit()
            if edited_prompt is None:
                click.echo("Editor closed without saving.", err=True)
                continue
            prompt = edited_prompt.strip()
        if prompt.strip().startswith("!fragment "):
            prompt, fragments, attachments = process_fragments_in_chat(db, prompt)

        if in_multi:
            if prompt.strip() == end_token:
                prompt = "\n".join(accumulated)
                fragments = accumulated_fragments
                attachments = accumulated_attachments
                in_multi = False
                accumulated = []
                accumulated_fragments = []
                accumulated_attachments = []
            else:
                if prompt:
                    accumulated.append(prompt)
                accumulated_fragments += fragments
                accumulated_attachments += attachments
                continue
        if template_obj:
            try:
                # Mirror prompt() logic: only pass input if template uses it
                uses_input = "input" in template_obj.vars()
                input_ = prompt if uses_input else ""
                template_prompt, template_system = template_obj.evaluate(input_, params)
            except Template.MissingVariables as ex:
                raise click.ClickException(str(ex))
            if template_system and not system:
                system = template_system
            if template_prompt:
                if prompt and not uses_input:
                    prompt = f"{template_prompt}\n{prompt}"
                else:
                    prompt = template_prompt
        if prompt.strip() in ("exit", "quit"):
            break

        response = conversation.chain(
            prompt,
            fragments=[str(fragment) for fragment in fragments],
            system_fragments=[
                str(system_fragment) for system_fragment in argument_system_fragments
            ],
            attachments=attachments,
            system=system,
            **kwargs,
        )

        # System prompt and system fragments only sent for the first message
        system = None
        argument_system_fragments = []
        for chunk in response:
            print(chunk, end="")
            sys.stdout.flush()
        response.log_to_db(db)
        print("")


def load_conversation(
    conversation_id: Optional[str],
    async_=False,
    database=None,
) -> Optional[_BaseConversation]:
    log_path = pathlib.Path(database) if database else logs_db_path()
    db = sqlite_utils.Database(log_path)
    migrate(db)
    if conversation_id is None:
        # Return the most recent conversation, or None if there are none
        matches = list(db["conversations"].rows_where(order_by="id desc", limit=1))
        if matches:
            conversation_id = matches[0]["id"]
        else:
            return None
    try:
        row = cast(sqlite_utils.db.Table, db["conversations"]).get(conversation_id)
    except sqlite_utils.db.NotFoundError:
        raise click.ClickException(
            "No conversation found with id={}".format(conversation_id)
        )
    # Inflate that conversation
    conversation_class = AsyncConversation if async_ else Conversation
    response_class = AsyncResponse if async_ else Response
    conversation = conversation_class.from_row(row)
    for response in db["responses"].rows_where(
        "conversation_id = ?", [conversation_id]
    ):
        conversation.responses.append(response_class.from_row(db, response))
    return conversation


@cli.group(
    cls=DefaultGroup,
    default="list",
    default_if_no_args=True,
)
def keys():
    "Manage stored API keys for different models"


@keys.command(name="list")
def keys_list():
    "List names of all stored keys"
    path = user_dir() / "keys.json"
    if not path.exists():
        click.echo("No keys found")
        return
    keys = json.loads(path.read_text())
    for key in sorted(keys.keys()):
        if key != "// Note":
            click.echo(key)


@keys.command(name="path")
def keys_path_command():
    "Output the path to the keys.json file"
    click.echo(user_dir() / "keys.json")


@keys.command(name="get")
@click.argument("name")
def keys_get(name):
    """
    Return the value of a stored key

    Example usage:

    \b
        export OPENAI_API_KEY=$(llm keys get openai)
    """
    path = user_dir() / "keys.json"
    if not path.exists():
        raise click.ClickException("No keys found")
    keys = json.loads(path.read_text())
    try:
        click.echo(keys[name])
    except KeyError:
        raise click.ClickException("No key found with name '{}'".format(name))


@keys.command(name="set")
@click.argument("name")
@click.option("--value", prompt="Enter key", hide_input=True, help="Value to set")
def keys_set(name, value):
    """
    Save a key in the keys.json file

    Example usage:

    \b
        $ llm keys set openai
        Enter key: ...
    """
    default = {"// Note": "This file stores secret API credentials. Do not share!"}
    path = user_dir() / "keys.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(default))
        path.chmod(0o600)
    try:
        current = json.loads(path.read_text())
    except json.decoder.JSONDecodeError:
        current = default
    current[name] = value
    path.write_text(json.dumps(current, indent=2) + "\n")


@cli.group(
    cls=DefaultGroup,
    default="list",
    default_if_no_args=True,
)
def logs():
    "Tools for exploring logged prompts and responses"


@logs.command(name="path")
def logs_path():
    "Output the path to the logs.db file"
    click.echo(logs_db_path())


@logs.command(name="status")
def logs_status():
    "Show current status of database logging"
    path = logs_db_path()
    if not path.exists():
        click.echo("No log database found at {}".format(path))
        return
    if logs_on():
        click.echo("Logging is ON for all prompts".format())
    else:
        click.echo("Logging is OFF".format())
    db = sqlite_utils.Database(path)
    migrate(db)
    click.echo("Found log database at {}".format(path))
    click.echo("Number of conversations logged:\t{}".format(db["conversations"].count))
    click.echo("Number of responses logged:\t{}".format(db["responses"].count))
    click.echo(
        "Database file size: \t\t{}".format(_human_readable_size(path.stat().st_size))
    )


@logs.command(name="backup")
@click.argument("path", type=click.Path(dir_okay=True, writable=True))
def backup(path):
    "Backup your logs database to this file"
    logs_path = logs_db_path()
    path = pathlib.Path(path)
    db = sqlite_utils.Database(logs_path)
    try:
        db.execute("vacuum into ?", [str(path)])
    except Exception as ex:
        raise click.ClickException(str(ex))
    click.echo(
        "Backed up {} to {}".format(_human_readable_size(path.stat().st_size), path)
    )


@logs.command(name="on")
def logs_turn_on():
    "Turn on logging for all prompts"
    path = user_dir() / "logs-off"
    if path.exists():
        path.unlink()


@logs.command(name="off")
def logs_turn_off():
    "Turn off logging for all prompts"
    path = user_dir() / "logs-off"
    path.touch()


LOGS_COLUMNS = """    responses.id,
    responses.model,
    responses.resolved_model,
    responses.prompt,
    responses.system,
    responses.prompt_json,
    responses.options_json,
    responses.response,
    responses.response_json,
    responses.conversation_id,
    responses.duration_ms,
    responses.datetime_utc,
    responses.input_tokens,
    responses.output_tokens,
    responses.token_details,
    conversations.name as conversation_name,
    conversations.model as conversation_model,
    schemas.content as schema_json"""

LOGS_SQL = """
select
{columns}
from
    responses
left join schemas on responses.schema_id = schemas.id
left join conversations on responses.conversation_id = conversations.id{extra_where}
order by {order_by}{limit}
"""
LOGS_SQL_SEARCH = """
select
{columns}
from
    responses
left join schemas on responses.schema_id = schemas.id
left join conversations on responses.conversation_id = conversations.id
join responses_fts on responses_fts.rowid = responses.rowid
where responses_fts match :query{extra_where}
order by {order_by}{limit}
"""

ATTACHMENTS_SQL = """
select
    response_id,
    attachments.id,
    attachments.type,
    attachments.path,
    attachments.url,
    length(attachments.content) as content_length
from attachments
join prompt_attachments
    on attachments.id = prompt_attachments.attachment_id
where prompt_attachments.response_id in ({})
order by prompt_attachments."order"
"""


@logs.command(name="list")
@click.option(
    "-n",
    "--count",
    type=int,
    default=None,
    help="Number of entries to show - defaults to 3, use 0 for all",
)
@click.option(
    "-p",
    "--path",
    type=click.Path(readable=True, exists=True, dir_okay=False),
    help="Path to log database",
    hidden=True,
)
@click.option(
    "-d",
    "--database",
    type=click.Path(readable=True, exists=True, dir_okay=False),
    help="Path to log database",
)
@click.option("-m", "--model", help="Filter by model or model alias")
@click.option("-q", "--query", help="Search for logs matching this string")
@click.option(
    "fragments",
    "--fragment",
    "-f",
    help="Filter for prompts using these fragments",
    multiple=True,
)
@click.option(
    "tools",
    "-T",
    "--tool",
    multiple=True,
    help="Filter for prompts with results from these tools",
)
@click.option(
    "any_tools",
    "--tools",
    is_flag=True,
    help="Filter for prompts with results from any tools",
)
@schema_option
@click.option(
    "--schema-multi",
    help="JSON schema used for multiple results",
)
@click.option(
    "-l", "--latest", is_flag=True, help="Return latest results matching search query"
)
@click.option(
    "--data", is_flag=True, help="Output newline-delimited JSON data for schema"
)
@click.option("--data-array", is_flag=True, help="Output JSON array of data for schema")
@click.option("--data-key", help="Return JSON objects from array in this key")
@click.option(
    "--data-ids", is_flag=True, help="Attach corresponding IDs to JSON objects"
)
@click.option("-t", "--truncate", is_flag=True, help="Truncate long strings in output")
@click.option(
    "-s", "--short", is_flag=True, help="Shorter YAML output with truncated prompts"
)
@click.option("-u", "--usage", is_flag=True, help="Include token usage")
@click.option("-r", "--response", is_flag=True, help="Just output the last response")
@click.option("-x", "--extract", is_flag=True, help="Extract first fenced code block")
@click.option(
    "extract_last",
    "--xl",
    "--extract-last",
    is_flag=True,
    help="Extract last fenced code block",
)
@click.option(
    "current_conversation",
    "-c",
    "--current",
    is_flag=True,
    flag_value=-1,
    help="Show logs from the current conversation",
)
@click.option(
    "conversation_id",
    "--cid",
    "--conversation",
    help="Show logs for this conversation ID",
)
@click.option("--id-gt", help="Return responses with ID > this")
@click.option("--id-gte", help="Return responses with ID >= this")
@click.option(
    "json_output",
    "--json",
    is_flag=True,
    help="Output logs as JSON",
)
@click.option(
    "--expand",
    "-e",
    is_flag=True,
    help="Expand fragments to show their content",
)
def logs_list(
    count,
    path,
    database,
    model,
    query,
    fragments,
    tools,
    any_tools,
    schema_input,
    schema_multi,
    latest,
    data,
    data_array,
    data_key,
    data_ids,
    truncate,
    short,
    usage,
    response,
    extract,
    extract_last,
    current_conversation,
    conversation_id,
    id_gt,
    id_gte,
    json_output,
    expand,
):
    "Show logged prompts and their responses"
    if database and not path:
        path = database
    path = pathlib.Path(path or logs_db_path())
    if not path.exists():
        raise click.ClickException("No log database found at {}".format(path))
    db = sqlite_utils.Database(path)
    migrate(db)

    if schema_multi:
        schema_input = schema_multi
    schema = resolve_schema_input(db, schema_input, load_template)
    if schema_multi:
        schema = multi_schema(schema)

    if short and (json_output or response):
        invalid = " or ".join(
            [
                flag[0]
                for flag in (("--json", json_output), ("--response", response))
                if flag[1]
            ]
        )
        raise click.ClickException("Cannot use --short and {} together".format(invalid))

    if response and not current_conversation and not conversation_id:
        current_conversation = True

    if current_conversation:
        try:
            conversation_id = next(
                db.query(
                    "select conversation_id from responses order by id desc limit 1"
                )
            )["conversation_id"]
        except StopIteration:
            # No conversations yet
            raise click.ClickException("No conversations found")

    # For --conversation set limit 0, if not explicitly set
    if count is None:
        if conversation_id:
            count = 0
        else:
            count = 3

    model_id = None
    if model:
        # Resolve alias, if any
        try:
            model_id = get_model(model).model_id
        except UnknownModelError:
            # Maybe they uninstalled a model, use the -m option as-is
            model_id = model

    sql = LOGS_SQL
    order_by = "responses.id desc"
    if query:
        sql = LOGS_SQL_SEARCH
        if not latest:
            order_by = "responses_fts.rank desc"

    limit = ""
    if count is not None and count > 0:
        limit = " limit {}".format(count)

    sql_format = {
        "limit": limit,
        "columns": LOGS_COLUMNS,
        "extra_where": "",
        "order_by": order_by,
    }
    where_bits = []
    sql_params = {
        "model": model_id,
        "query": query,
        "conversation_id": conversation_id,
        "id_gt": id_gt,
        "id_gte": id_gte,
    }
    if model_id:
        where_bits.append("responses.model = :model")
    if conversation_id:
        where_bits.append("responses.conversation_id = :conversation_id")
    if id_gt:
        where_bits.append("responses.id > :id_gt")
    if id_gte:
        where_bits.append("responses.id >= :id_gte")
    if fragments:
        # Resolve the fragments to their hashes
        fragment_hashes = [
            fragment.id() for fragment in resolve_fragments(db, fragments)
        ]
        exists_clauses = []

        for i, fragment_hash in enumerate(fragment_hashes):
            exists_clause = f"""
            exists (
                select 1 from prompt_fragments
                where prompt_fragments.response_id = responses.id
                and prompt_fragments.fragment_id in (
                    select fragments.id from fragments
                    where hash = :f{i}
                )
                union
                select 1 from system_fragments
                where system_fragments.response_id = responses.id
                and system_fragments.fragment_id in (
                    select fragments.id from fragments
                    where hash = :f{i}
                )
            )
            """
            exists_clauses.append(exists_clause)
            sql_params["f{}".format(i)] = fragment_hash

        where_bits.append(" and ".join(exists_clauses))

    if any_tools:
        # Any response that involved at least one tool result
        where_bits.append(
            """
            exists (
              select 1
                from tool_results
              where
                tool_results.response_id = responses.id
            )
        """
        )
    if tools:
        tools_by_name = get_tools()
        # Filter responses by tools (must have ALL of the named tools, including plugin)
        tool_clauses = []
        for i, tool_name in enumerate(tools):
            try:
                plugin_name = tools_by_name[tool_name].plugin
            except KeyError:
                raise click.ClickException(f"Unknown tool: {tool_name}")

            tool_clauses.append(
                f"""
            exists (
              select 1
                from tool_results
                join tools on tools.id = tool_results.tool_id
               where tool_results.response_id = responses.id
                 and tools.name = :tool{i}
                 and tools.plugin = :plugin{i}
            )
            """
            )
            sql_params[f"tool{i}"] = tool_name
            sql_params[f"plugin{i}"] = plugin_name

        # AND means “must have all” — use OR instead if you want “any of”
        where_bits.append(" and ".join(tool_clauses))

    schema_id = None
    if schema:
        schema_id = make_schema_id(schema)[0]
        where_bits.append("responses.schema_id = :schema_id")
        sql_params["schema_id"] = schema_id

    if where_bits:
        where_ = " and " if query else " where "
        sql_format["extra_where"] = where_ + " and ".join(where_bits)

    final_sql = sql.format(**sql_format)
    rows = list(db.query(final_sql, sql_params))

    # Reverse the order - we do this because we 'order by id desc limit 3' to get the
    # 3 most recent results, but we still want to display them in chronological order
    # ... except for searches where we don't do this
    if not query and not data:
        rows.reverse()

    # Fetch any attachments
    ids = [row["id"] for row in rows]
    attachments = list(db.query(ATTACHMENTS_SQL.format(",".join("?" * len(ids))), ids))
    attachments_by_id = {}
    for attachment in attachments:
        attachments_by_id.setdefault(attachment["response_id"], []).append(attachment)

    FRAGMENTS_SQL = """
    select
        {table}.response_id,
        fragments.hash,
        fragments.id as fragment_id,
        fragments.content,
        (
            select json_group_array(fragment_aliases.alias)
            from fragment_aliases
            where fragment_aliases.fragment_id = fragments.id
        ) as aliases
    from {table}
    join fragments on {table}.fragment_id = fragments.id
    where {table}.response_id in ({placeholders})
    order by {table}."order"
    """

    # Fetch any prompt or system prompt fragments
    prompt_fragments_by_id = {}
    system_fragments_by_id = {}
    for table, dictionary in (
        ("prompt_fragments", prompt_fragments_by_id),
        ("system_fragments", system_fragments_by_id),
    ):
        for fragment in db.query(
            FRAGMENTS_SQL.format(placeholders=",".join("?" * len(ids)), table=table),
            ids,
        ):
            dictionary.setdefault(fragment["response_id"], []).append(fragment)

    if data or data_array or data_key or data_ids:
        # Special case for --data to output valid JSON
        to_output = []
        for row in rows:
            response = row["response"] or ""
            try:
                decoded = json.loads(response)
                new_items = []
                if (
                    isinstance(decoded, dict)
                    and (data_key in decoded)
                    and all(isinstance(item, dict) for item in decoded[data_key])
                ):
                    for item in decoded[data_key]:
                        new_items.append(item)
                else:
                    new_items.append(decoded)
                if data_ids:
                    for item in new_items:
                        item[find_unused_key(item, "response_id")] = row["id"]
                        item[find_unused_key(item, "conversation_id")] = row["id"]
                to_output.extend(new_items)
            except ValueError:
                pass
        for line in output_rows_as_json(to_output, nl=not data_array, compact=True):
            click.echo(line)
        return

    # Tool usage information
    TOOLS_SQL = """
    SELECT responses.id,
    -- Tools related to this response
    COALESCE(
        (SELECT json_group_array(json_object(
            'id', t.id,
            'hash', t.hash,
            'name', t.name,
            'description', t.description,
            'input_schema', json(t.input_schema)
        ))
        FROM tools t
        JOIN tool_responses tr ON t.id = tr.tool_id
        WHERE tr.response_id = responses.id
        ),
        '[]'
    ) AS tools,
    -- Tool calls for this response
    COALESCE(
        (SELECT json_group_array(json_object(
            'id', tc.id,
            'tool_id', tc.tool_id,
            'name', tc.name,
            'arguments', json(tc.arguments),
            'tool_call_id', tc.tool_call_id
        ))
        FROM tool_calls tc
        WHERE tc.response_id = responses.id
        ),
        '[]'
    ) AS tool_calls,
    -- Tool results for this response
    COALESCE(
        (SELECT json_group_array(json_object(
            'id', tr.id,
            'tool_id', tr.tool_id,
            'name', tr.name,
            'output', tr.output,
            'tool_call_id', tr.tool_call_id,
            'exception', tr.exception,
            'attachments', COALESCE(
                (SELECT json_group_array(json_object(
                    'id', a.id,
                    'type', a.type,
                    'path', a.path,
                    'url', a.url,
                    'content', a.content
                ))
                FROM tool_results_attachments tra
                JOIN attachments a ON tra.attachment_id = a.id
                WHERE tra.tool_result_id = tr.id
                ),
                '[]'
            )
        ))
        FROM tool_results tr
        WHERE tr.response_id = responses.id
        ),
        '[]'
    ) AS tool_results
    FROM responses
    where id in ({placeholders})
    """
    tool_info_by_id = {
        row["id"]: {
            "tools": json.loads(row["tools"]),
            "tool_calls": json.loads(row["tool_calls"]),
            "tool_results": json.loads(row["tool_results"]),
        }
        for row in db.query(
            TOOLS_SQL.format(placeholders=",".join("?" * len(ids))), ids
        )
    }

    for row in rows:
        if truncate:
            row["prompt"] = truncate_string(row["prompt"] or "")
            row["response"] = truncate_string(row["response"] or "")
        # Add prompt and system fragments
        for key in ("prompt_fragments", "system_fragments"):
            row[key] = [
                {
                    "hash": fragment["hash"],
                    "content": (
                        fragment["content"]
                        if expand
                        else truncate_string(fragment["content"])
                    ),
                    "aliases": json.loads(fragment["aliases"]),
                }
                for fragment in (
                    prompt_fragments_by_id.get(row["id"], [])
                    if key == "prompt_fragments"
                    else system_fragments_by_id.get(row["id"], [])
                )
            ]
        # Either decode or remove all JSON keys
        keys = list(row.keys())
        for key in keys:
            if key.endswith("_json") and row[key] is not None:
                if truncate:
                    del row[key]
                else:
                    row[key] = json.loads(row[key])
        row.update(tool_info_by_id[row["id"]])

    output = None
    if json_output:
        # Output as JSON if requested
        for row in rows:
            row["attachments"] = [
                {k: v for k, v in attachment.items() if k != "response_id"}
                for attachment in attachments_by_id.get(row["id"], [])
            ]
        output = json.dumps(list(rows), indent=2)
    elif extract or extract_last:
        # Extract and return first code block
        for row in rows:
            output = extract_fenced_code_block(row["response"], last=extract_last)
            if output is not None:
                break
    elif response:
        # Just output the last response
        if rows:
            output = rows[-1]["response"]

    if output is not None:
        click.echo(output)
    else:
        # Output neatly formatted human-readable logs
        def _display_fragments(fragments, title):
            if not fragments:
                return
            if not expand:
                content = "\n".join(
                    ["- {}".format(fragment["hash"]) for fragment in fragments]
                )
            else:
                # <details><summary> for each one
                bits = []
                for fragment in fragments:
                    bits.append(
                        "<details><summary>{}</summary>\n{}\n</details>".format(
                            fragment["hash"], maybe_fenced_code(fragment["content"])
                        )
                    )
                content = "\n".join(bits)
            click.echo(f"\n### {title}\n\n{content}")

        current_system = None
        should_show_conversation = True
        for row in rows:
            if short:
                system = truncate_string(
                    row["system"] or "", 120, normalize_whitespace=True
                )
                prompt = truncate_string(
                    row["prompt"] or "", 120, normalize_whitespace=True, keep_end=True
                )
                cid = row["conversation_id"]
                attachments = attachments_by_id.get(row["id"])
                obj = {
                    "model": row["model"],
                    "datetime": row["datetime_utc"].split(".")[0],
                    "conversation": cid,
                }
                if row["tool_calls"]:
                    obj["tool_calls"] = [
                        "{}({})".format(
                            tool_call["name"], json.dumps(tool_call["arguments"])
                        )
                        for tool_call in row["tool_calls"]
                    ]
                if row["tool_results"]:
                    obj["tool_results"] = [
                        "{}: {}".format(
                            tool_result["name"], truncate_string(tool_result["output"])
                        )
                        for tool_result in row["tool_results"]
                    ]
                if system:
                    obj["system"] = system
                if prompt:
                    obj["prompt"] = prompt
                if attachments:
                    items = []
                    for attachment in attachments:
                        details = {"type": attachment["type"]}
                        if attachment.get("path"):
                            details["path"] = attachment["path"]
                        if attachment.get("url"):
                            details["url"] = attachment["url"]
                        items.append(details)
                    obj["attachments"] = items
                for key in ("prompt_fragments", "system_fragments"):
                    obj[key] = [fragment["hash"] for fragment in row[key]]
                if usage and (row["input_tokens"] or row["output_tokens"]):
                    usage_details = {
                        "input": row["input_tokens"],
                        "output": row["output_tokens"],
                    }
                    if row["token_details"]:
                        usage_details["details"] = json.loads(row["token_details"])
                    obj["usage"] = usage_details
                click.echo(yaml.dump([obj], sort_keys=False).strip())
                continue
            # Not short, output Markdown
            click.echo(
                "# {}{}\n{}".format(
                    row["datetime_utc"].split(".")[0],
                    (
                        "    conversation: {} id: {}".format(
                            row["conversation_id"], row["id"]
                        )
                        if should_show_conversation
                        else ""
                    ),
                    (
                        (
                            "\nModel: **{}**{}\n".format(
                                row["model"],
                                (
                                    " (resolved: **{}**)".format(row["resolved_model"])
                                    if row["resolved_model"]
                                    else ""
                                ),
                            )
                        )
                        if should_show_conversation
                        else ""
                    ),
                )
            )
            # In conversation log mode only show it for the first one
            if conversation_id:
                should_show_conversation = False
            click.echo("## Prompt\n\n{}".format(row["prompt"] or "-- none --"))
            _display_fragments(row["prompt_fragments"], "Prompt fragments")
            if row["system"] != current_system:
                if row["system"] is not None:
                    click.echo("\n## System\n\n{}".format(row["system"]))
                current_system = row["system"]
            _display_fragments(row["system_fragments"], "System fragments")
            if row["schema_json"]:
                click.echo(
                    "\n## Schema\n\n```json\n{}\n```".format(
                        json.dumps(row["schema_json"], indent=2)
                    )
                )
            # Show tool calls and results
            if row["tools"]:
                click.echo("\n### Tools\n")
                for tool in row["tools"]:
                    click.echo(
                        "- **{}**: `{}`<br>\n    {}<br>\n    Arguments: {}".format(
                            tool["name"],
                            tool["hash"],
                            tool["description"],
                            json.dumps(tool["input_schema"]["properties"]),
                        )
                    )
            if row["tool_results"]:
                click.echo("\n### Tool results\n")
                for tool_result in row["tool_results"]:
                    attachments = ""
                    for attachment in tool_result["attachments"]:
                        desc = ""
                        if attachment.get("type"):
                            desc += attachment["type"] + ": "
                        if attachment.get("path"):
                            desc += attachment["path"]
                        elif attachment.get("url"):
                            desc += attachment["url"]
                        elif attachment.get("content"):
                            desc += f"<{attachment['content_length']:,} bytes>"
                        attachments += "\n    - {}".format(desc)
                    click.echo(
                        "- **{}**: `{}`<br>\n{}{}{}".format(
                            tool_result["name"],
                            tool_result["tool_call_id"],
                            textwrap.indent(tool_result["output"], "    "),
                            (
                                "<br>\n    **Error**: {}\n".format(
                                    tool_result["exception"]
                                )
                                if tool_result["exception"]
                                else ""
                            ),
                            attachments,
                        )
                    )
            attachments = attachments_by_id.get(row["id"])
            if attachments:
                click.echo("\n### Attachments\n")
                for i, attachment in enumerate(attachments, 1):
                    if attachment["path"]:
                        path = attachment["path"]
                        click.echo(
                            "{}. **{}**: `{}`".format(i, attachment["type"], path)
                        )
                    elif attachment["url"]:
                        click.echo(
                            "{}. **{}**: {}".format(
                                i, attachment["type"], attachment["url"]
                            )
                        )
                    elif attachment["content_length"]:
                        click.echo(
                            "{}. **{}**: `<{} bytes>`".format(
                                i,
                                attachment["type"],
                                f"{attachment['content_length']:,}",
                            )
                        )

            # If a schema was provided and the row is valid JSON, pretty print and syntax highlight it
            response = row["response"]
            if row["schema_json"]:
                try:
                    parsed = json.loads(response)
                    response = "```json\n{}\n```".format(json.dumps(parsed, indent=2))
                except ValueError:
                    pass
            click.echo("\n## Response\n")
            if row["tool_calls"]:
                click.echo("### Tool calls\n")
                for tool_call in row["tool_calls"]:
                    click.echo(
                        "- **{}**: `{}`<br>\n    Arguments: {}".format(
                            tool_call["name"],
                            tool_call["tool_call_id"],
                            json.dumps(tool_call["arguments"]),
                        )
                    )
                click.echo("")
            if response:
                click.echo("{}\n".format(response))
            if usage:
                token_usage = token_usage_string(
                    row["input_tokens"],
                    row["output_tokens"],
                    json.loads(row["token_details"]) if row["token_details"] else None,
                )
                if token_usage:
                    click.echo("## Token usage\n\n{}\n".format(token_usage))


@cli.group(
    cls=DefaultGroup,
    default="list",
    default_if_no_args=True,
)
def models():
    "Manage available models"


_type_lookup = {
    "number": "float",
    "integer": "int",
    "string": "str",
    "object": "dict",
}


@models.command(name="list")
@click.option(
    "--options", is_flag=True, help="Show options for each model, if available"
)
@click.option("async_", "--async", is_flag=True, help="List async models")
@click.option("--schemas", is_flag=True, help="List models that support schemas")
@click.option("--tools", is_flag=True, help="List models that support tools")
@click.option(
    "-q",
    "--query",
    multiple=True,
    help="Search for models matching these strings",
)
@click.option("model_ids", "-m", "--model", help="Specific model IDs", multiple=True)
def models_list(options, async_, schemas, tools, query, model_ids):
    "List available models"
    models_that_have_shown_options = set()
    for model_with_aliases in get_models_with_aliases():
        if async_ and not model_with_aliases.async_model:
            continue
        if query:
            # Only show models where every provided query string matches
            if not all(model_with_aliases.matches(q) for q in query):
                continue
        if model_ids:
            ids_and_aliases = set(
                [model_with_aliases.model.model_id] + model_with_aliases.aliases
            )
            if not ids_and_aliases.intersection(model_ids):
                continue
        if schemas and not model_with_aliases.model.supports_schema:
            continue
        if tools and not model_with_aliases.model.supports_tools:
            continue
        extra_info = []
        if model_with_aliases.aliases:
            extra_info.append(
                "aliases: {}".format(", ".join(model_with_aliases.aliases))
            )
        model = (
            model_with_aliases.model if not async_ else model_with_aliases.async_model
        )
        output = str(model)
        if extra_info:
            output += " ({})".format(", ".join(extra_info))
        if options and model.Options.model_json_schema()["properties"]:
            output += "\n  Options:"
            for name, field in model.Options.model_json_schema()["properties"].items():
                any_of = field.get("anyOf")
                if any_of is None:
                    any_of = [{"type": field.get("type", "str")}]
                types = ", ".join(
                    [
                        _type_lookup.get(item.get("type"), item.get("type", "str"))
                        for item in any_of
                        if item.get("type") != "null"
                    ]
                )
                bits = ["\n    ", name, ": ", types]
                description = field.get("description", "")
                if description and (
                    model.__class__ not in models_that_have_shown_options
                ):
                    wrapped = textwrap.wrap(description, 70)
                    bits.append("\n      ")
                    bits.extend("\n      ".join(wrapped))
                output += "".join(bits)
            models_that_have_shown_options.add(model.__class__)
        if options and model.attachment_types:
            attachment_types = ", ".join(sorted(model.attachment_types))
            wrapper = textwrap.TextWrapper(
                width=min(max(shutil.get_terminal_size().columns, 30), 70),
                initial_indent="    ",
                subsequent_indent="    ",
            )
            output += "\n  Attachment types:\n{}".format(wrapper.fill(attachment_types))
        features = (
            []
            + (["streaming"] if model.can_stream else [])
            + (["schemas"] if model.supports_schema else [])
            + (["tools"] if model.supports_tools else [])
            + (["async"] if model_with_aliases.async_model else [])
        )
        if options and features:
            output += "\n  Features:\n{}".format(
                "\n".join("  - {}".format(feature) for feature in features)
            )
        if options and hasattr(model, "needs_key") and model.needs_key:
            output += "\n  Keys:"
            if hasattr(model, "needs_key") and model.needs_key:
                output += "\n    key: {}".format(model.needs_key)
            if hasattr(model, "key_env_var") and model.key_env_var:
                output += "\n    env_var: {}".format(model.key_env_var)
        click.echo(output)
    if not query and not options and not schemas and not model_ids:
        click.echo(f"Default: {get_default_model()}")


@models.command(name="default")
@click.argument("model", required=False)
def models_default(model):
    "Show or set the default model"
    if not model:
        click.echo(get_default_model())
        return
    # Validate it is a known model
    try:
        model = get_model(model)
        set_default_model(model.model_id)
    except KeyError:
        raise click.ClickException("Unknown model: {}".format(model))


@cli.group(
    cls=DefaultGroup,
    default="list",
    default_if_no_args=True,
)
def templates():
    "Manage stored prompt templates"


@templates.command(name="list")
def templates_list():
    "List available prompt templates"
    path = template_dir()
    pairs = []
    for file in path.glob("*.yaml"):
        name = file.stem
        try:
            template = load_template(name)
        except LoadTemplateError:
            # Skip invalid templates
            continue
        text = []
        if template.system:
            text.append(f"system: {template.system}")
            if template.prompt:
                text.append(f" prompt: {template.prompt}")
        else:
            text = [template.prompt if template.prompt else ""]
        pairs.append((name, "".join(text).replace("\n", " ")))
    try:
        max_name_len = max(len(p[0]) for p in pairs)
    except ValueError:
        return
    else:
        fmt = "{name:<" + str(max_name_len) + "} : {prompt}"
        for name, prompt in sorted(pairs):
            text = fmt.format(name=name, prompt=prompt)
            click.echo(display_truncated(text))


@templates.command(name="show")
@click.argument("name")
def templates_show(name):
    "Show the specified prompt template"
    try:
        template = load_template(name)
    except LoadTemplateError:
        raise click.ClickException(f"Template '{name}' not found or invalid")
    click.echo(
        yaml.dump(
            dict((k, v) for k, v in template.model_dump().items() if v is not None),
            indent=4,
            default_flow_style=False,
        )
    )


@templates.command(name="edit")
@click.argument("name")
def templates_edit(name):
    "Edit the specified prompt template using the default $EDITOR"
    # First ensure it exists
    path = template_dir() / f"{name}.yaml"
    if not path.exists():
        path.write_text(DEFAULT_TEMPLATE, "utf-8")
    click.edit(filename=str(path))
    # Validate that template
    load_template(name)


@templates.command(name="path")
def templates_path():
    "Output the path to the templates directory"
    click.echo(template_dir())


@templates.command(name="loaders")
def templates_loaders():
    "Show template loaders registered by plugins"
    found = False
    for prefix, loader in get_template_loaders().items():
        found = True
        docs = "Undocumented"
        if loader.__doc__:
            docs = textwrap.dedent(loader.__doc__).strip()
        click.echo(f"{prefix}:")
        click.echo(textwrap.indent(docs, "  "))
    if not found:
        click.echo("No template loaders found")


@cli.group(
    cls=DefaultGroup,
    default="list",
    default_if_no_args=True,
)
def schemas():
    "Manage stored schemas"


@schemas.command(name="list")
@click.option(
    "-p",
    "--path",
    type=click.Path(readable=True, exists=True, dir_okay=False),
    help="Path to log database",
    hidden=True,
)
@click.option(
    "-d",
    "--database",
    type=click.Path(readable=True, exists=True, dir_okay=False),
    help="Path to log database",
)
@click.option(
    "queries",
    "-q",
    "--query",
    multiple=True,
    help="Search for schemas matching this string",
)
@click.option("--full", is_flag=True, help="Output full schema contents")
@click.option("json_", "--json", is_flag=True, help="Output as JSON")
@click.option("nl", "--nl", is_flag=True, help="Output as newline-delimited JSON")
def schemas_list(path, database, queries, full, json_, nl):
    "List stored schemas"
    if database and not path:
        path = database
    path = pathlib.Path(path or logs_db_path())
    if not path.exists():
        raise click.ClickException("No log database found at {}".format(path))
    db = sqlite_utils.Database(path)
    migrate(db)

    params = []
    where_sql = ""
    if queries:
        where_bits = ["schemas.content like ?" for _ in queries]
        where_sql += " where {}".format(" and ".join(where_bits))
        params.extend("%{}%".format(q) for q in queries)

    sql = """
    select
      schemas.id,
      schemas.content,
      max(responses.datetime_utc) as recently_used,
      count(*) as times_used
    from schemas
    join responses
      on responses.schema_id = schemas.id
    {} group by responses.schema_id
    order by recently_used
    """.format(
        where_sql
    )
    rows = db.query(sql, params)

    if json_ or nl:
        for line in output_rows_as_json(rows, json_cols={"content"}, nl=nl):
            click.echo(line)
        return

    for row in rows:
        click.echo("- id: {}".format(row["id"]))
        if full:
            click.echo(
                "  schema: |\n{}".format(
                    textwrap.indent(
                        json.dumps(json.loads(row["content"]), indent=2), "    "
                    )
                )
            )
        else:
            click.echo(
                "  summary: |\n    {}".format(
                    schema_summary(json.loads(row["content"]))
                )
            )
        click.echo(
            "  usage: |\n    {} time{}, most recently {}".format(
                row["times_used"],
                "s" if row["times_used"] != 1 else "",
                row["recently_used"],
            )
        )


@schemas.command(name="show")
@click.argument("schema_id")
@click.option(
    "-p",
    "--path",
    type=click.Path(readable=True, exists=True, dir_okay=False),
    help="Path to log database",
    hidden=True,
)
@click.option(
    "-d",
    "--database",
    type=click.Path(readable=True, exists=True, dir_okay=False),
    help="Path to log database",
)
def schemas_show(schema_id, path, database):
    "Show a stored schema"
    if database and not path:
        path = database
    path = pathlib.Path(path or logs_db_path())
    if not path.exists():
        raise click.ClickException("No log database found at {}".format(path))
    db = sqlite_utils.Database(path)
    migrate(db)

    try:
        row = db["schemas"].get(schema_id)
    except sqlite_utils.db.NotFoundError:
        raise click.ClickException("Invalid schema ID")
    click.echo(json.dumps(json.loads(row["content"]), indent=2))


@schemas.command(name="dsl")
@click.argument("input")
@click.option("--multi", is_flag=True, help="Wrap in an array")
def schemas_dsl_debug(input, multi):
    """
    Convert LLM's schema DSL to a JSON schema

    \b
        llm schema dsl 'name, age int, bio: their bio'
    """
    schema = schema_dsl(input, multi)
    click.echo(json.dumps(schema, indent=2))


@cli.group(
    cls=DefaultGroup,
    default="list",
    default_if_no_args=True,
)
def tools():
    "Manage tools that can be made available to LLMs"


@tools.command(name="list")
@click.argument("tool_defs", nargs=-1)
@click.option("json_", "--json", is_flag=True, help="Output as JSON")
@click.option(
    "python_tools",
    "--functions",
    help="Python code block or file path defining functions to register as tools",
    multiple=True,
)
def tools_list(tool_defs, json_, python_tools):
    "List available tools that have been provided by plugins"

    def introspect_tools(toolbox_class):
        methods = []
        for tool in toolbox_class.method_tools():
            methods.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "arguments": tool.input_schema,
                    "implementation": tool.implementation,
                }
            )
        return methods

    if tool_defs:
        tools = {}
        for tool in _gather_tools(tool_defs, python_tools):
            if hasattr(tool, "name"):
                tools[tool.name] = tool
            else:
                tools[tool.__class__.__name__] = tool
    else:
        tools = get_tools()
        if python_tools:
            for code_or_path in python_tools:
                for tool in _tools_from_code(code_or_path):
                    tools[tool.name] = tool

    output_tools = []
    output_toolboxes = []
    tool_objects = []
    toolbox_objects = []
    for name, tool in sorted(tools.items()):
        if isinstance(tool, Tool):
            tool_objects.append(tool)
            output_tools.append(
                {
                    "name": name,
                    "description": tool.description,
                    "arguments": tool.input_schema,
                    "plugin": tool.plugin,
                }
            )
        else:
            toolbox_objects.append(tool)
            output_toolboxes.append(
                {
                    "name": name,
                    "tools": [
                        {
                            "name": tool["name"],
                            "description": tool["description"],
                            "arguments": tool["arguments"],
                        }
                        for tool in introspect_tools(tool)
                    ],
                }
            )
    if json_:
        click.echo(
            json.dumps(
                {"tools": output_tools, "toolboxes": output_toolboxes},
                indent=2,
            )
        )
    else:
        for tool in tool_objects:
            sig = "()"
            if tool.implementation:
                sig = str(inspect.signature(tool.implementation))
            click.echo(
                "{}{}{}\n".format(
                    tool.name,
                    sig,
                    " (plugin: {})".format(tool.plugin) if tool.plugin else "",
                )
            )
            if tool.description:
                click.echo(textwrap.indent(tool.description.strip(), "  ") + "\n")
        for toolbox in toolbox_objects:
            click.echo(toolbox.name + ":\n")
            for tool in toolbox.method_tools():
                sig = (
                    str(inspect.signature(tool.implementation))
                    .replace("(self, ", "(")
                    .replace("(self)", "()")
                )
                click.echo(
                    "  {}{}\n".format(
                        tool.name,
                        sig,
                    )
                )
                if tool.description:
                    click.echo(textwrap.indent(tool.description.strip(), "    ") + "\n")


@cli.group(
    cls=DefaultGroup,
    default="list",
    default_if_no_args=True,
)
def aliases():
    "Manage model aliases"


@aliases.command(name="list")
@click.option("json_", "--json", is_flag=True, help="Output as JSON")
def aliases_list(json_):
    "List current aliases"
    to_output = []
    for alias, model in get_model_aliases().items():
        if alias != model.model_id:
            to_output.append((alias, model.model_id, ""))
    for alias, embedding_model in get_embedding_model_aliases().items():
        if alias != embedding_model.model_id:
            to_output.append((alias, embedding_model.model_id, "embedding"))
    if json_:
        click.echo(
            json.dumps({key: value for key, value, type_ in to_output}, indent=4)
        )
        return
    max_alias_length = max(len(a) for a, _, _ in to_output)
    fmt = "{alias:<" + str(max_alias_length) + "} : {model_id}{type_}"
    for alias, model_id, type_ in to_output:
        click.echo(
            fmt.format(
                alias=alias, model_id=model_id, type_=f" ({type_})" if type_ else ""
            )
        )


@aliases.command(name="set")
@click.argument("alias")
@click.argument("model_id", required=False)
@click.option(
    "-q",
    "--query",
    multiple=True,
    help="Set alias for model matching these strings",
)
def aliases_set(alias, model_id, query):
    """
    Set an alias for a model

    Example usage:

    \b
        llm aliases set mini gpt-4o-mini

    Alternatively you can omit the model ID and specify one or more -q options.
    The first model matching all of those query strings will be used.

    \b
        llm aliases set mini -q 4o -q mini
    """
    if not model_id:
        if not query:
            raise click.ClickException(
                "You must provide a model_id or at least one -q option"
            )
        # Search for the first model matching all query strings
        found = None
        for model_with_aliases in get_models_with_aliases():
            if all(model_with_aliases.matches(q) for q in query):
                found = model_with_aliases
                break
        if not found:
            raise click.ClickException(
                "No model found matching query: " + ", ".join(query)
            )
        model_id = found.model.model_id
        set_alias(alias, model_id)
        click.echo(
            f"Alias '{alias}' set to model '{model_id}'",
            err=True,
        )
    else:
        set_alias(alias, model_id)


@aliases.command(name="remove")
@click.argument("alias")
def aliases_remove(alias):
    """
    Remove an alias

    Example usage:

    \b
        $ llm aliases remove turbo
    """
    try:
        remove_alias(alias)
    except KeyError as ex:
        raise click.ClickException(ex.args[0])


@aliases.command(name="path")
def aliases_path():
    "Output the path to the aliases.json file"
    click.echo(user_dir() / "aliases.json")


@cli.group(
    cls=DefaultGroup,
    default="list",
    default_if_no_args=True,
)
def fragments():
    """
    Manage fragments that are stored in the database

    Fragments are reusable snippets of text that are shared across multiple prompts.
    """


@fragments.command(name="list")
@click.option(
    "queries",
    "-q",
    "--query",
    multiple=True,
    help="Search for fragments matching these strings",
)
@click.option("--aliases", is_flag=True, help="Show only fragments with aliases")
@click.option("json_", "--json", is_flag=True, help="Output as JSON")
def fragments_list(queries, aliases, json_):
    "List current fragments"
    db = sqlite_utils.Database(logs_db_path())
    migrate(db)
    params = {}
    param_count = 0
    where_bits = []
    if aliases:
        where_bits.append("fragment_aliases.alias is not null")
    for q in queries:
        param_count += 1
        p = f"p{param_count}"
        params[p] = q
        where_bits.append(
            f"""
            (fragments.hash = :{p} or fragment_aliases.alias = :{p}
            or fragments.source like '%' || :{p} || '%'
            or fragments.content like '%' || :{p} || '%')
        """
        )
    where = "\n      and\n  ".join(where_bits)
    if where:
        where = " where " + where
    sql = """
    select
        fragments.hash,
        json_group_array(fragment_aliases.alias) filter (
            where
            fragment_aliases.alias is not null
        ) as aliases,
        fragments.datetime_utc,
        fragments.source,
        fragments.content
    from
        fragments
    left join
        fragment_aliases on fragment_aliases.fragment_id = fragments.id
    {where}
    group by
        fragments.id, fragments.hash, fragments.content, fragments.datetime_utc, fragments.source
    order by fragments.datetime_utc
    """.format(
        where=where
    )
    results = list(db.query(sql, params))
    for result in results:
        result["aliases"] = json.loads(result["aliases"])
    if json_:
        click.echo(json.dumps(results, indent=4))
    else:
        yaml.add_representer(
            str,
            lambda dumper, data: dumper.represent_scalar(
                "tag:yaml.org,2002:str", data, style="|" if "\n" in data else None
            ),
        )
        for result in results:
            result["content"] = truncate_string(result["content"])
            click.echo(yaml.dump([result], sort_keys=False, width=sys.maxsize).strip())


@fragments.command(name="set")
@click.argument("alias", callback=validate_fragment_alias)
@click.argument("fragment")
def fragments_set(alias, fragment):
    """
    Set an alias for a fragment

    Accepts an alias and a file path, URL, hash or '-' for stdin

    Example usage:

    \b
        llm fragments set mydocs ./docs.md
    """
    db = sqlite_utils.Database(logs_db_path())
    migrate(db)
    try:
        resolved = resolve_fragments(db, [fragment])[0]
    except FragmentNotFound as ex:
        raise click.ClickException(str(ex))
    migrate(db)
    alias_sql = """
    insert into fragment_aliases (alias, fragment_id)
    values (:alias, :fragment_id)
    on conflict(alias) do update set
        fragment_id = excluded.fragment_id;
    """
    with db.conn:
        fragment_id = ensure_fragment(db, resolved)
        db.conn.execute(alias_sql, {"alias": alias, "fragment_id": fragment_id})


@fragments.command(name="show")
@click.argument("alias_or_hash")
def fragments_show(alias_or_hash):
    """
    Display the fragment stored under an alias or hash

    \b
        llm fragments show mydocs
    """
    db = sqlite_utils.Database(logs_db_path())
    migrate(db)
    try:
        resolved = resolve_fragments(db, [alias_or_hash])[0]
    except FragmentNotFound as ex:
        raise click.ClickException(str(ex))
    click.echo(resolved)


@fragments.command(name="remove")
@click.argument("alias", callback=validate_fragment_alias)
def fragments_remove(alias):
    """
    Remove a fragment alias

    Example usage:

    \b
        llm fragments remove docs
    """
    db = sqlite_utils.Database(logs_db_path())
    migrate(db)
    with db.conn:
        db.conn.execute(
            "delete from fragment_aliases where alias = :alias", {"alias": alias}
        )


@fragments.command(name="loaders")
def fragments_loaders():
    """Show fragment loaders registered by plugins"""
    from llm import get_fragment_loaders

    found = False
    for prefix, loader in get_fragment_loaders().items():
        if found:
            # Extra newline on all after the first
            click.echo("")
        found = True
        docs = "Undocumented"
        if loader.__doc__:
            docs = textwrap.dedent(loader.__doc__).strip()
        click.echo(f"{prefix}:")
        click.echo(textwrap.indent(docs, "  "))
    if not found:
        click.echo("No fragment loaders found")


@cli.command(name="plugins")
@click.option("--all", help="Include built-in default plugins", is_flag=True)
@click.option(
    "hooks", "--hook", help="Filter for plugins that implement this hook", multiple=True
)
def plugins_list(all, hooks):
    "List installed plugins"
    plugins = get_plugins(all)
    hooks = set(hooks)
    if hooks:
        plugins = [plugin for plugin in plugins if hooks.intersection(plugin["hooks"])]
    click.echo(json.dumps(plugins, indent=2))


def display_truncated(text):
    console_width = shutil.get_terminal_size()[0]
    if len(text) > console_width:
        return text[: console_width - 3] + "..."
    else:
        return text


@cli.command()
@click.argument("packages", nargs=-1, required=False)
@click.option(
    "-U", "--upgrade", is_flag=True, help="Upgrade packages to latest version"
)
@click.option(
    "-e",
    "--editable",
    help="Install a project in editable mode from this path",
)
@click.option(
    "--force-reinstall",
    is_flag=True,
    help="Reinstall all packages even if they are already up-to-date",
)
@click.option(
    "--no-cache-dir",
    is_flag=True,
    help="Disable the cache",
)
@click.option(
    "--pre",
    is_flag=True,
    help="Include pre-release and development versions",
)
def install(packages, upgrade, editable, force_reinstall, no_cache_dir, pre):
    """Install packages from PyPI into the same environment as LLM"""
    args = ["pip", "install"]
    if upgrade:
        args += ["--upgrade"]
    if editable:
        args += ["--editable", editable]
    if force_reinstall:
        args += ["--force-reinstall"]
    if no_cache_dir:
        args += ["--no-cache-dir"]
    if pre:
        args += ["--pre"]
    args += list(packages)
    sys.argv = args
    run_module("pip", run_name="__main__")


@cli.command()
@click.argument("packages", nargs=-1, required=True)
@click.option("-y", "--yes", is_flag=True, help="Don't ask for confirmation")
def uninstall(packages, yes):
    """Uninstall Python packages from the LLM environment"""
    sys.argv = ["pip", "uninstall"] + list(packages) + (["-y"] if yes else [])
    run_module("pip", run_name="__main__")


@cli.command()
@click.argument("collection", required=False)
@click.argument("id", required=False)
@click.option(
    "-i",
    "--input",
    type=click.Path(exists=True, readable=True, allow_dash=True),
    help="File to embed",
)
@click.option(
    "-m", "--model", help="Embedding model to use", envvar="LLM_EMBEDDING_MODEL"
)
@click.option("--store", is_flag=True, help="Store the text itself in the database")
@click.option(
    "-d",
    "--database",
    type=click.Path(file_okay=True, allow_dash=False, dir_okay=False, writable=True),
    envvar="LLM_EMBEDDINGS_DB",
)
@click.option(
    "-c",
    "--content",
    help="Content to embed",
)
@click.option("--binary", is_flag=True, help="Treat input as binary data")
@click.option(
    "--metadata",
    help="JSON object metadata to store",
    callback=json_validator("metadata"),
)
@click.option(
    "format_",
    "-f",
    "--format",
    type=click.Choice(["json", "blob", "base64", "hex"]),
    help="Output format",
)
def embed(
    collection, id, input, model, store, database, content, binary, metadata, format_
):
    """Embed text and store or return the result"""
    if collection and not id:
        raise click.ClickException("Must provide both collection and id")

    if store and not collection:
        raise click.ClickException("Must provide collection when using --store")

    # Lazy load this because we do not need it for -c or -i versions
    def get_db():
        if database:
            return sqlite_utils.Database(database)
        else:
            return sqlite_utils.Database(user_dir() / "embeddings.db")

    collection_obj = None
    model_obj = None
    if collection:
        db = get_db()
        if Collection.exists(db, collection):
            # Load existing collection and use its model
            collection_obj = Collection(collection, db)
            model_obj = collection_obj.model()
        else:
            # We will create a new one, but that means model is required
            if not model:
                model = get_default_embedding_model()
                if model is None:
                    raise click.ClickException(
                        "You need to specify an embedding model (no default model is set)"
                    )
            collection_obj = Collection(collection, db=db, model_id=model)
            model_obj = collection_obj.model()

    if model_obj is None:
        if model is None:
            model = get_default_embedding_model()
        try:
            model_obj = get_embedding_model(model)
        except UnknownModelError:
            raise click.ClickException(
                "You need to specify an embedding model (no default model is set)"
            )

    show_output = True
    if collection and (format_ is None):
        show_output = False

    # Resolve input text
    if not content:
        if not input or input == "-":
            # Read from stdin
            input_source = sys.stdin.buffer if binary else sys.stdin
            content = input_source.read()
        else:
            mode = "rb" if binary else "r"
            with open(input, mode) as f:
                content = f.read()

    if not content:
        raise click.ClickException("No content provided")

    if collection_obj:
        embedding = collection_obj.embed(id, content, metadata=metadata, store=store)
    else:
        embedding = model_obj.embed(content)

    if show_output:
        if format_ == "json" or format_ is None:
            click.echo(json.dumps(embedding))
        elif format_ == "blob":
            click.echo(encode(embedding))
        elif format_ == "base64":
            click.echo(base64.b64encode(encode(embedding)).decode("ascii"))
        elif format_ == "hex":
            click.echo(encode(embedding).hex())


@cli.command()
@click.argument("collection")
@click.argument(
    "input_path",
    type=click.Path(exists=True, dir_okay=False, allow_dash=True, readable=True),
    required=False,
)
@click.option(
    "--format",
    type=click.Choice(["json", "csv", "tsv", "nl"]),
    help="Format of input file - defaults to auto-detect",
)
@click.option(
    "--files",
    type=(click.Path(file_okay=False, dir_okay=True, allow_dash=False), str),
    multiple=True,
    help="Embed files in this directory - specify directory and glob pattern",
)
@click.option(
    "encodings",
    "--encoding",
    help="Encodings to try when reading --files",
    multiple=True,
)
@click.option("--binary", is_flag=True, help="Treat --files as binary data")
@click.option("--sql", help="Read input using this SQL query")
@click.option(
    "--attach",
    type=(str, click.Path(file_okay=True, dir_okay=False, allow_dash=False)),
    multiple=True,
    help="Additional databases to attach - specify alias and file path",
)
@click.option(
    "--batch-size", type=int, help="Batch size to use when running embeddings"
)
@click.option("--prefix", help="Prefix to add to the IDs", default="")
@click.option(
    "-m", "--model", help="Embedding model to use", envvar="LLM_EMBEDDING_MODEL"
)
@click.option(
    "--prepend",
    help="Prepend this string to all content before embedding",
)
@click.option("--store", is_flag=True, help="Store the text itself in the database")
@click.option(
    "-d",
    "--database",
    type=click.Path(file_okay=True, allow_dash=False, dir_okay=False, writable=True),
    envvar="LLM_EMBEDDINGS_DB",
)
def embed_multi(
    collection,
    input_path,
    format,
    files,
    encodings,
    binary,
    sql,
    attach,
    batch_size,
    prefix,
    model,
    prepend,
    store,
    database,
):
    """
    Store embeddings for multiple strings at once in the specified collection.

    Input data can come from one of three sources:

    \b
    1. A CSV, TSV, JSON or JSONL file:
       - CSV/TSV: First column is ID, remaining columns concatenated as content
       - JSON: Array of objects with "id" field and content fields
       - JSONL: Newline-delimited JSON objects

    \b
       Examples:
         llm embed-multi docs input.csv
         cat data.json | llm embed-multi docs -
         llm embed-multi docs input.json --format json

    \b
    2. A SQL query against a SQLite database:
       - First column returned is used as ID
       - Other columns concatenated to form content

    \b
       Examples:
         llm embed-multi docs --sql "SELECT id, title, body FROM posts"
         llm embed-multi docs --attach blog blog.db --sql "SELECT id, content FROM blog.posts"

    \b
    3. Files in directories matching glob patterns:
       - Each file becomes one embedding
       - Relative file paths become IDs

    \b
       Examples:
         llm embed-multi docs --files docs '**/*.md'
         llm embed-multi images --files photos '*.jpg' --binary
         llm embed-multi texts --files texts '*.txt' --encoding utf-8 --encoding latin-1
    """
    if binary and not files:
        raise click.UsageError("--binary must be used with --files")
    if binary and encodings:
        raise click.UsageError("--binary cannot be used with --encoding")
    if not input_path and not sql and not files:
        raise click.UsageError("Either --sql or input path or --files is required")

    if files:
        if input_path or sql or format:
            raise click.UsageError(
                "Cannot use --files with --sql, input path or --format"
            )

    if database:
        db = sqlite_utils.Database(database)
    else:
        db = sqlite_utils.Database(user_dir() / "embeddings.db")

    for alias, attach_path in attach:
        db.attach(alias, attach_path)

    try:
        collection_obj = Collection(
            collection, db=db, model_id=model or get_default_embedding_model()
        )
    except ValueError:
        raise click.ClickException(
            "You need to specify an embedding model (no default model is set)"
        )

    expected_length = None
    if files:
        encodings = encodings or ("utf-8", "latin-1")

        def count_files():
            i = 0
            for directory, pattern in files:
                for path in pathlib.Path(directory).glob(pattern):
                    i += 1
            return i

        def iterate_files():
            for directory, pattern in files:
                p = pathlib.Path(directory)
                if not p.exists() or not p.is_dir():
                    # fixes issue/274 - raise error if directory does not exist
                    raise click.UsageError(f"Invalid directory: {directory}")
                for path in pathlib.Path(directory).glob(pattern):
                    if path.is_dir():
                        continue  # fixed issue/280 - skip directories
                    relative = path.relative_to(directory)
                    content = None
                    if binary:
                        content = path.read_bytes()
                    else:
                        for encoding in encodings:
                            try:
                                content = path.read_text(encoding=encoding)
                            except UnicodeDecodeError:
                                continue
                    if content is None:
                        # Log to stderr
                        click.echo(
                            "Could not decode text in file {}".format(path),
                            err=True,
                        )
                    else:
                        yield {"id": str(relative), "content": content}

        expected_length = count_files()
        rows = iterate_files()
    elif sql:
        rows = db.query(sql)
        count_sql = "select count(*) as c from ({})".format(sql)
        expected_length = next(db.query(count_sql))["c"]
    else:

        def load_rows(fp):
            return rows_from_file(fp, Format[format.upper()] if format else None)[0]

        try:
            if input_path != "-":
                # Read the file twice - first time is to get a count
                expected_length = 0
                with open(input_path, "rb") as fp:
                    for _ in load_rows(fp):
                        expected_length += 1

            rows = load_rows(
                open(input_path, "rb")
                if input_path != "-"
                else io.BufferedReader(sys.stdin.buffer)
            )
        except json.JSONDecodeError as ex:
            raise click.ClickException(str(ex))

    with click.progressbar(
        rows, label="Embedding", show_percent=True, length=expected_length
    ) as rows:

        def tuples() -> Iterable[Tuple[str, Union[bytes, str]]]:
            for row in rows:
                values = list(row.values())
                id: str = prefix + str(values[0])
                content: Optional[Union[bytes, str]] = None
                if binary:
                    content = cast(bytes, values[1])
                else:
                    content = " ".join(v or "" for v in values[1:])
                if prepend and isinstance(content, str):
                    content = prepend + content
                yield id, content or ""

        embed_kwargs = {"store": store}
        if batch_size:
            embed_kwargs["batch_size"] = batch_size
        collection_obj.embed_multi(tuples(), **embed_kwargs)


@cli.command()
@click.argument("collection")
@click.argument("id", required=False)
@click.option(
    "-i",
    "--input",
    type=click.Path(exists=True, readable=True, allow_dash=True),
    help="File to embed for comparison",
)
@click.option("-c", "--content", help="Content to embed for comparison")
@click.option("--binary", is_flag=True, help="Treat input as binary data")
@click.option(
    "-n", "--number", type=int, default=10, help="Number of results to return"
)
@click.option("-p", "--plain", is_flag=True, help="Output in plain text format")
@click.option(
    "-d",
    "--database",
    type=click.Path(file_okay=True, allow_dash=False, dir_okay=False, writable=True),
    envvar="LLM_EMBEDDINGS_DB",
)
@click.option("--prefix", help="Just IDs with this prefix", default="")
def similar(collection, id, input, content, binary, number, plain, database, prefix):
    """
    Return top N similar IDs from a collection using cosine similarity.

    Example usage:

    \b
        llm similar my-collection -c "I like cats"

    Or to find content similar to a specific stored ID:

    \b
        llm similar my-collection 1234
    """
    if not id and not content and not input:
        raise click.ClickException("Must provide content or an ID for the comparison")

    if database:
        db = sqlite_utils.Database(database)
    else:
        db = sqlite_utils.Database(user_dir() / "embeddings.db")

    if not db["embeddings"].exists():
        raise click.ClickException("No embeddings table found in database")

    try:
        collection_obj = Collection(collection, db, create=False)
    except Collection.DoesNotExist:
        raise click.ClickException("Collection does not exist")

    if id:
        try:
            results = collection_obj.similar_by_id(id, number, prefix=prefix)
        except Collection.DoesNotExist:
            raise click.ClickException("ID not found in collection")
    else:
        # Resolve input text
        if not content:
            if not input or input == "-":
                # Read from stdin
                input_source = sys.stdin.buffer if binary else sys.stdin
                content = input_source.read()
            else:
                mode = "rb" if binary else "r"
                with open(input, mode) as f:
                    content = f.read()
        if not content:
            raise click.ClickException("No content provided")
        results = collection_obj.similar(content, number, prefix=prefix)

    for result in results:
        if plain:
            click.echo(f"{result.id} ({result.score})\n")
            if result.content:
                click.echo(textwrap.indent(result.content, "  "))
            if result.metadata:
                click.echo(textwrap.indent(json.dumps(result.metadata), "  "))
            click.echo("")
        else:
            click.echo(json.dumps(asdict(result)))


@cli.group(
    cls=DefaultGroup,
    default="list",
    default_if_no_args=True,
)
def embed_models():
    "Manage available embedding models"


@embed_models.command(name="list")
@click.option(
    "-q",
    "--query",
    multiple=True,
    help="Search for embedding models matching these strings",
)
def embed_models_list(query):
    "List available embedding models"
    output = []
    for model_with_aliases in get_embedding_models_with_aliases():
        if query:
            if not all(model_with_aliases.matches(q) for q in query):
                continue
        s = str(model_with_aliases.model)
        if model_with_aliases.aliases:
            s += " (aliases: {})".format(", ".join(model_with_aliases.aliases))
        output.append(s)
    click.echo("\n".join(output))


@embed_models.command(name="default")
@click.argument("model", required=False)
@click.option(
    "--remove-default", is_flag=True, help="Reset to specifying no default model"
)
def embed_models_default(model, remove_default):
    "Show or set the default embedding model"
    if not model and not remove_default:
        default = get_default_embedding_model()
        if default is None:
            click.echo("<No default embedding model set>", err=True)
        else:
            click.echo(default)
        return
    # Validate it is a known model
    try:
        if remove_default:
            set_default_embedding_model(None)
        else:
            model = get_embedding_model(model)
            set_default_embedding_model(model.model_id)
    except KeyError:
        raise click.ClickException("Unknown embedding model: {}".format(model))


@cli.group(
    cls=DefaultGroup,
    default="list",
    default_if_no_args=True,
)
def collections():
    "View and manage collections of embeddings"


@collections.command(name="path")
def collections_path():
    "Output the path to the embeddings database"
    click.echo(user_dir() / "embeddings.db")


@collections.command(name="list")
@click.option(
    "-d",
    "--database",
    type=click.Path(file_okay=True, allow_dash=False, dir_okay=False, writable=True),
    envvar="LLM_EMBEDDINGS_DB",
    help="Path to embeddings database",
)
@click.option("json_", "--json", is_flag=True, help="Output as JSON")
def embed_db_collections(database, json_):
    "View a list of collections"
    database = database or (user_dir() / "embeddings.db")
    db = sqlite_utils.Database(str(database))
    if not db["collections"].exists():
        raise click.ClickException("No collections table found in {}".format(database))
    rows = db.query(
        """
    select
        collections.name,
        collections.model,
        count(embeddings.id) as num_embeddings
    from
        collections left join embeddings
        on collections.id = embeddings.collection_id
    group by
        collections.name, collections.model
    """
    )
    if json_:
        click.echo(json.dumps(list(rows), indent=4))
    else:
        for row in rows:
            click.echo("{}: {}".format(row["name"], row["model"]))
            click.echo(
                "  {} embedding{}".format(
                    row["num_embeddings"], "s" if row["num_embeddings"] != 1 else ""
                )
            )


@collections.command(name="delete")
@click.argument("collection")
@click.option(
    "-d",
    "--database",
    type=click.Path(file_okay=True, allow_dash=False, dir_okay=False, writable=True),
    envvar="LLM_EMBEDDINGS_DB",
    help="Path to embeddings database",
)
def collections_delete(collection, database):
    """
    Delete the specified collection

    Example usage:

    \b
        llm collections delete my-collection
    """
    database = database or (user_dir() / "embeddings.db")
    db = sqlite_utils.Database(str(database))
    try:
        collection_obj = Collection(collection, db, create=False)
    except Collection.DoesNotExist:
        raise click.ClickException("Collection does not exist")
    collection_obj.delete()


@models.group(
    cls=DefaultGroup,
    default="list",
    default_if_no_args=True,
)
def options():
    "Manage default options for models"


@options.command(name="list")
def options_list():
    """
    List default options for all models

    Example usage:

    \b
        llm models options list
    """
    options = get_all_model_options()
    if not options:
        click.echo("No default options set for any models.", err=True)
        return

    for model_id, model_options in options.items():
        click.echo(f"{model_id}:")
        for key, value in model_options.items():
            click.echo(f"  {key}: {value}")


@options.command(name="show")
@click.argument("model")
def options_show(model):
    """
    List default options set for a specific model

    Example usage:

    \b
        llm models options show gpt-4o
    """
    import llm

    try:
        # Resolve alias to model ID
        model_obj = llm.get_model(model)
        model_id = model_obj.model_id
    except llm.UnknownModelError:
        # Use as-is if not found
        model_id = model

    options = get_model_options(model_id)
    if not options:
        click.echo(f"No default options set for model '{model_id}'.", err=True)
        return

    for key, value in options.items():
        click.echo(f"{key}: {value}")


@options.command(name="set")
@click.argument("model")
@click.argument("key")
@click.argument("value")
def options_set(model, key, value):
    """
    Set a default option for a model

    Example usage:

    \b
        llm models options set gpt-4o temperature 0.5
    """
    import llm

    try:
        # Resolve alias to model ID
        model_obj = llm.get_model(model)
        model_id = model_obj.model_id

        # Validate option against model schema
        try:
            # Create a test Options object to validate
            test_options = {key: value}
            model_obj.Options(**test_options)
        except pydantic.ValidationError as ex:
            raise click.ClickException(render_errors(ex.errors()))

    except llm.UnknownModelError:
        # Use as-is if not found
        model_id = model

    set_model_option(model_id, key, value)
    click.echo(f"Set default option {key}={value} for model {model_id}", err=True)


@options.command(name="clear")
@click.argument("model")
@click.argument("key", required=False)
def options_clear(model, key):
    """
    Clear default option(s) for a model

    Example usage:

    \b
        llm models options clear gpt-4o
        # Or for a single option
        llm models options clear gpt-4o temperature
    """
    import llm

    try:
        # Resolve alias to model ID
        model_obj = llm.get_model(model)
        model_id = model_obj.model_id
    except llm.UnknownModelError:
        # Use as-is if not found
        model_id = model

    cleared_keys = []
    if not key:
        cleared_keys = list(get_model_options(model_id).keys())
        for key_ in cleared_keys:
            clear_model_option(model_id, key_)
    else:
        cleared_keys.append(key)
        clear_model_option(model_id, key)
    if cleared_keys:
        if len(cleared_keys) == 1:
            click.echo(f"Cleared option '{cleared_keys[0]}' for model {model_id}")
        else:
            click.echo(
                f"Cleared {', '.join(cleared_keys)} options for model {model_id}"
            )


def template_dir():
    path = user_dir() / "templates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_db_path():
    return user_dir() / "logs.db"


def get_history(chat_id):
    if chat_id is None:
        return None, []
    log_path = logs_db_path()
    db = sqlite_utils.Database(log_path)
    migrate(db)
    if chat_id == -1:
        # Return the most recent chat
        last_row = list(db["logs"].rows_where(order_by="-id", limit=1))
        if last_row:
            chat_id = last_row[0].get("chat_id") or last_row[0].get("id")
        else:  # Database is empty
            return None, []
    rows = db["logs"].rows_where(
        "id = ? or chat_id = ?", [chat_id, chat_id], order_by="id"
    )
    return chat_id, rows


def render_errors(errors):
    output = []
    for error in errors:
        output.append(", ".join(error["loc"]))
        output.append("  " + error["msg"])
    return "\n".join(output)


load_plugins()

pm.hook.register_commands(cli=cli)


def _human_readable_size(size_bytes):
    if size_bytes == 0:
        return "0B"

    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = 0

    while size_bytes >= 1024 and i < len(size_name) - 1:
        size_bytes /= 1024.0
        i += 1

    return "{:.2f}{}".format(size_bytes, size_name[i])


def logs_on():
    return not (user_dir() / "logs-off").exists()


def get_all_model_options() -> dict:
    """
    Get all default options for all models
    """
    path = user_dir() / "model_options.json"
    if not path.exists():
        return {}

    try:
        options = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}

    return options


def get_model_options(model_id: str) -> dict:
    """
    Get default options for a specific model

    Args:
        model_id: Return options for model with this ID

    Returns:
        A dictionary of model options
    """
    path = user_dir() / "model_options.json"
    if not path.exists():
        return {}

    try:
        options = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}

    return options.get(model_id, {})


def set_model_option(model_id: str, key: str, value: Any) -> None:
    """
    Set a default option for a model.

    Args:
        model_id: The model ID
        key: The option key
        value: The option value
    """
    path = user_dir() / "model_options.json"
    if path.exists():
        try:
            options = json.loads(path.read_text())
        except json.JSONDecodeError:
            options = {}
    else:
        options = {}

    # Ensure the model has an entry
    if model_id not in options:
        options[model_id] = {}

    # Set the option
    options[model_id][key] = value

    # Save the options
    path.write_text(json.dumps(options, indent=2))


def clear_model_option(model_id: str, key: str) -> None:
    """
    Clear a model option

    Args:
        model_id: The model ID
        key: Key to clear
    """
    path = user_dir() / "model_options.json"
    if not path.exists():
        return

    try:
        options = json.loads(path.read_text())
    except json.JSONDecodeError:
        return

    if model_id not in options:
        return

    if key in options[model_id]:
        del options[model_id][key]
        if not options[model_id]:
            del options[model_id]

    path.write_text(json.dumps(options, indent=2))


class LoadTemplateError(ValueError):
    pass


def _parse_yaml_template(name, content):
    try:
        loaded = yaml.safe_load(content)
    except yaml.YAMLError as ex:
        raise LoadTemplateError("Invalid YAML: {}".format(str(ex)))
    if isinstance(loaded, str):
        return Template(name=name, prompt=loaded)
    loaded["name"] = name
    try:
        return Template(**loaded)
    except pydantic.ValidationError as ex:
        msg = "A validation error occurred:\n"
        msg += render_errors(ex.errors())
        raise LoadTemplateError(msg)


def load_template(name: str) -> Template:
    "Load template, or raise LoadTemplateError(msg)"
    if name.startswith("https://") or name.startswith("http://"):
        response = httpx.get(name)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as ex:
            raise LoadTemplateError("Could not load template {}: {}".format(name, ex))
        return _parse_yaml_template(name, response.text)

    potential_path = pathlib.Path(name)

    if has_plugin_prefix(name) and not potential_path.exists():
        prefix, rest = name.split(":", 1)
        loaders = get_template_loaders()
        if prefix not in loaders:
            raise LoadTemplateError("Unknown template prefix: {}".format(prefix))
        loader = loaders[prefix]
        try:
            return loader(rest)
        except Exception as ex:
            raise LoadTemplateError("Could not load template {}: {}".format(name, ex))

    # Try local file
    if potential_path.exists():
        path = potential_path
    else:
        # Look for template in template_dir()
        path = template_dir() / f"{name}.yaml"
    if not path.exists():
        raise LoadTemplateError(f"Invalid template: {name}")
    content = path.read_text()
    template_obj = _parse_yaml_template(name, content)
    # We trust functions here because they came from the filesystem
    template_obj._functions_is_trusted = True
    return template_obj


def _tools_from_code(code_or_path: str) -> List[Tool]:
    """
    Treat all Python functions in the code as tools
    """
    if "\n" not in code_or_path and code_or_path.endswith(".py"):
        try:
            code_or_path = pathlib.Path(code_or_path).read_text()
        except FileNotFoundError:
            raise click.ClickException("File not found: {}".format(code_or_path))
    namespace: Dict[str, Any] = {}
    tools = []
    try:
        exec(code_or_path, namespace)
    except SyntaxError as ex:
        raise click.ClickException("Error in --functions definition: {}".format(ex))
    # Register all callables in the locals dict:
    for name, value in namespace.items():
        if callable(value) and not name.startswith("_"):
            tools.append(Tool.function(value))
    return tools


def _debug_tool_call(_, tool_call, tool_result):
    click.echo(
        click.style(
            "\nTool call: {}({})".format(tool_call.name, tool_call.arguments),
            fg="yellow",
            bold=True,
        ),
        err=True,
    )
    output = ""
    attachments = ""
    if tool_result.attachments:
        attachments += "\nAttachments:\n"
        for attachment in tool_result.attachments:
            attachments += f"  {repr(attachment)}\n"

    try:
        output = json.dumps(json.loads(tool_result.output), indent=2)
    except ValueError:
        output = tool_result.output
    output += attachments
    click.echo(
        click.style(
            textwrap.indent(output, "  ") + ("\n" if not tool_result.exception else ""),
            fg="green",
            bold=True,
        ),
        err=True,
    )
    if tool_result.exception:
        click.echo(
            click.style(
                "  Exception: {}".format(tool_result.exception),
                fg="red",
                bold=True,
            ),
            err=True,
        )


def _approve_tool_call(_, tool_call):
    click.echo(
        click.style(
            "Tool call: {}({})".format(tool_call.name, tool_call.arguments),
            fg="yellow",
            bold=True,
        ),
        err=True,
    )
    if not click.confirm("Approve tool call?"):
        raise CancelToolCall("User cancelled tool call")


def _gather_tools(
    tool_specs: List[str], python_tools: List[str]
) -> List[Union[Tool, Type[Toolbox]]]:
    tools: List[Union[Tool, Type[Toolbox]]] = []
    if python_tools:
        for code_or_path in python_tools:
            tools.extend(_tools_from_code(code_or_path))
    registered_tools = get_tools()
    registered_classes = dict(
        (key, value)
        for key, value in registered_tools.items()
        if inspect.isclass(value)
    )
    bad_tools = [
        tool for tool in tool_specs if tool.split("(")[0] not in registered_tools
    ]
    if bad_tools:
        raise click.ClickException(
            "Tool(s) {} not found. Available tools: {}".format(
                ", ".join(bad_tools), ", ".join(registered_tools.keys())
            )
        )
    for tool_spec in tool_specs:
        if not tool_spec[0].isupper():
            # It's a function
            tools.append(registered_tools[tool_spec])
        else:
            # It's a class
            tools.append(instantiate_from_spec(registered_classes, tool_spec))
    return tools


def _get_conversation_tools(conversation, tools):
    if conversation and not tools and conversation.responses:
        # Copy plugin tools from first response in conversation
        initial_tools = conversation.responses[0].prompt.tools
        if initial_tools:
            # Only tools from plugins:
            return [tool.name for tool in initial_tools if tool.plugin]

# Prompt Library Commands
@cli.group(name="prompts")
def prompts_group():
    """Manage prompt library - save, organize and reuse prompts"""
    pass


@prompts_group.command(name="add")
@click.argument("name")
@click.option("--prompt", required=True, help="Prompt template text")
@click.option("--system", "system_prompt", help="System prompt")
@click.option("--description", help="Brief description")
@click.option("--category", help="Category name")
@click.option("--tags", help="Comma-separated tags")
@click.option("--model", help="Preferred model")
@click.option("--file", "prompt_file", type=click.File('r'), help="Load prompt from file")
def prompts_add(name, prompt, system_prompt, description, category, tags, model, prompt_file):
    """Add a new prompt to the library"""
    from llm.prompt_library import PromptLibrary
    
    if prompt_file:
        prompt = prompt_file.read()
    
    tags_list = [t.strip() for t in tags.split(",")] if tags else None
    
    library = PromptLibrary()
    try:
        prompt_id = library.add_prompt(
            name=name,
            prompt=prompt,
            system_prompt=system_prompt,
            description=description,
            category=category,
            tags=tags_list,
            model=model
        )
        click.echo(f"Prompt '{name}' added successfully (ID: {prompt_id})")
    except Exception as e:
        raise click.ClickException(str(e))


@prompts_group.command(name="list")
@click.option("--category", help="Filter by category")
@click.option("--tag", help="Filter by tag")
@click.option("--author", help="Filter by author")
@click.option("--limit", type=int, help="Limit number of results")
@click.option("--format", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table")
def prompts_list(category, tag, author, limit, output_format):
    """List saved prompts"""
    from llm.prompt_library import PromptLibrary
    import json
    import yaml
    
    library = PromptLibrary()
    prompts = library.list_prompts(category=category, tag=tag, author=author, limit=limit)
    
    if output_format == "json":
        click.echo(json.dumps(prompts, indent=2))
    elif output_format == "yaml":
        click.echo(yaml.dump(prompts, default_flow_style=False))
    else:
        # Table format
        if not prompts:
            click.echo("No prompts found")
            return
        
        click.echo(f"\nPrompt Library ({len(prompts)} prompts)\n")
        click.echo(f"{'Name':<20} {'Category':<15} {'Tags':<30} {'Used':<8}")
        click.echo("=" * 80)
        for p in prompts:
            tags_str = ", ".join(p.get('tags') or [])[:28]
            click.echo(f"{p['name']:<20} {(p.get('category') or ''):<15} {tags_str:<30} {p['usage_count']:<8}")


@prompts_group.command(name="show")
@click.argument("name")
def prompts_show(name):
    """Show details of a prompt"""
    from llm.prompt_library import PromptLibrary
    
    library = PromptLibrary()
    prompt = library.get_prompt(name)
    
    if not prompt:
        raise click.ClickException(f"Prompt '{name}' not found")
    
    click.echo(f"\nPrompt: {prompt['name']}")
    click.echo("=" * 60)
    if prompt.get('description'):
        click.echo(f"Description: {prompt['description']}")
    if prompt.get('category'):
        click.echo(f"Category: {prompt['category']}")
    if prompt.get('tags'):
        click.echo(f"Tags: {', '.join(prompt['tags'])}")
    if prompt.get('model'):
        click.echo(f"Model: {prompt['model']}")
    click.echo(f"Created: {prompt['created_at']}")
    click.echo(f"Used: {prompt['usage_count']} times")
    
    click.echo(f"\nPrompt Template:")
    click.echo("-" * 60)
    click.echo(prompt['prompt'])
    
    if prompt.get('system_prompt'):
        click.echo(f"\nSystem Prompt:")
        click.echo("-" * 60)
        click.echo(prompt['system_prompt'])


@prompts_group.command(name="use")
@click.argument("name")
@click.option("--var", "variables", multiple=True, help="Variable in format key=value")
@click.option("--vars", "vars_file", type=click.File('r'), help="JSON/YAML file with variables")
@click.option("-m", "--model", help="Override default model")
def prompts_use(name, variables, vars_file, model):
    """Use a saved prompt"""
    from llm.prompt_library import PromptLibrary
    import json
    import yaml
    import re
    
    library = PromptLibrary()
    prompt = library.get_prompt(name)
    
    if not prompt:
        raise click.ClickException(f"Prompt '{name}' not found")
    
    # Parse variables
    var_dict = {}
    if vars_file:
        content = vars_file.read()
        try:
            var_dict = json.loads(content)
        except:
            var_dict = yaml.safe_load(content)
    
    for var in variables:
        if '=' not in var:
            raise click.ClickException(f"Variable must be in format key=value, got: {var}")
        key, value = var.split('=', 1)
        var_dict[key] = value
    
    # Substitute variables in prompt
    prompt_text = prompt['prompt']
    for key, value in var_dict.items():
        prompt_text = prompt_text.replace(f"{{{key}}}", value)
    
    # Check for unsubstituted variables
    unsubstituted = re.findall(r'\{(\w+)\}', prompt_text)
    if unsubstituted:
        raise click.ClickException(f"Missing variables: {', '.join(unsubstituted)}")
    
    # Execute the prompt
    from llm import get_model
    
    model_id = model or prompt.get('model')
    llm_model = get_model(model_id)
    
    system = prompt.get('system_prompt')
    response = llm_model.prompt(prompt_text, system=system)
    
    click.echo(response.text())
    
    # Track usage
    library.increment_usage(name, cost=0.0, success=True)


@prompts_group.command(name="edit")
@click.argument("name")
@click.option("--prompt", help="New prompt template")
@click.option("--system", "system_prompt", help="New system prompt")
@click.option("--description", help="New description")
@click.option("--category", help="New category")
@click.option("--tags", help="New tags (comma-separated)")
@click.option("--create-version", is_flag=True, help="Create new version instead of overwriting")
def prompts_edit(name, prompt, system_prompt, description, category, tags, create_version):
    """Edit an existing prompt"""
    from llm.prompt_library import PromptLibrary
    
    library = PromptLibrary()
    tags_list = [t.strip() for t in tags.split(",")] if tags else None
    
    success = library.update_prompt(
        name=name,
        prompt=prompt,
        system_prompt=system_prompt,
        description=description,
        category=category,
        tags=tags_list,
        create_version=create_version
    )
    
    if success:
        click.echo(f"Prompt '{name}' updated successfully")
    else:
        raise click.ClickException(f"Prompt '{name}' not found")


@prompts_group.command(name="delete")
@click.argument("name")
@click.option("--force", is_flag=True, help="Don't ask for confirmation")
def prompts_delete(name, force):
    """Delete a prompt from the library"""
    from llm.prompt_library import PromptLibrary
    
    if not force:
        if not click.confirm(f"Delete prompt '{name}'?"):
            return
    
    library = PromptLibrary()
    success = library.delete_prompt(name)
    
    if success:
        click.echo(f"Prompt '{name}' deleted")
    else:
        raise click.ClickException(f"Prompt '{name}' not found")


@prompts_group.command(name="search")
@click.argument("query")
def prompts_search(query):
    """Search prompts by name or description"""
    from llm.prompt_library import PromptLibrary
    
    library = PromptLibrary()
    prompts = library.search_prompts(query)
    
    if not prompts:
        click.echo("No prompts found")
        return
    
    click.echo(f"\nFound {len(prompts)} prompts:\n")
    click.echo(f"{'Name':<20} {'Description':<40} {'Used':<8}")
    click.echo("=" * 70)
    for p in prompts:
        desc = (p.get('description') or '')[:38]
        click.echo(f"{p['name']:<20} {desc:<40} {p['usage_count']:<8}")


@prompts_group.command(name="export")
@click.argument("name")
@click.option("--format", "output_format", type=click.Choice(["yaml", "json"]), default="yaml")
@click.option("--output", type=click.File('w'), help="Output file (default: stdout)")
def prompts_export(name, output_format, output):
    """Export a prompt to YAML or JSON"""
    from llm.prompt_library import PromptLibrary
    
    library = PromptLibrary()
    exported = library.export_prompt(name, format=output_format)
    
    if not exported:
        raise click.ClickException(f"Prompt '{name}' not found")
    
    if output:
        output.write(exported)
        click.echo(f"Prompt '{name}' exported to {output.name}", err=True)
    else:
        click.echo(exported)


@prompts_group.command(name="import")
@click.argument("source", type=click.File('r'))
@click.option("--format", "input_format", type=click.Choice(["yaml", "json"]), default="yaml")
@click.option("--overwrite", is_flag=True, help="Overwrite if exists")
def prompts_import(source, input_format, overwrite):
    """Import a prompt from YAML or JSON file"""
    from llm.prompt_library import PromptLibrary
    
    library = PromptLibrary()
    data = source.read()
    
    try:
        name = library.import_prompt(data, format=input_format, overwrite=overwrite)
        click.echo(f"Prompt '{name}' imported successfully")
    except Exception as e:
        raise click.ClickException(str(e))


# Cost Tracking Commands
@cli.group(name="costs")
def costs_group():
    """Track API costs and manage budgets"""
    pass


@costs_group.command(name="show")
@click.option("--period", type=click.Choice(["today", "week", "month", "year", "all"]), default="month")
@click.option("--project", help="Filter by project")
@click.option("--model", help="Filter by model")
@click.option("--detailed", is_flag=True, help="Show detailed breakdown")
def costs_show(period, project, model, detailed):
    """Show cost summary"""
    from llm.cost_tracking import CostTracker
    
    tracker = CostTracker()
    spending = tracker.get_spending(period=period, project=project, model=model)
    
    click.echo(f"\nCost Summary ({period})")
    click.echo("=" * 60)
    click.echo(f"Total Cost:        ${spending['total_cost']:.4f}")
    click.echo(f"Total Prompts:     {spending['total_prompts']}")
    click.echo(f"Total Tokens:      {spending['total_tokens']:,}")
    if spending['total_prompts'] > 0:
        click.echo(f"Avg Cost/Prompt:   ${spending['avg_cost_per_prompt']:.4f}")
    
    if detailed and spending['by_model']:
        click.echo(f"\nBy Model:")
        click.echo("-" * 60)
        for model_name, stats in sorted(spending['by_model'].items(), key=lambda x: x[1]['cost'], reverse=True):
            pct = (stats['cost'] / spending['total_cost'] * 100) if spending['total_cost'] > 0 else 0
            click.echo(f"  {model_name:<20} ${stats['cost']:.4f} ({pct:.1f}%) - {stats['prompts']} prompts")


@costs_group.command(name="set-budget")
@click.argument("amount", type=float)
@click.option("--name", default="default", help="Budget name")
@click.option("--period", type=click.Choice(["daily", "weekly", "monthly", "yearly"]), default="monthly")
@click.option("--project", help="Budget for specific project")
@click.option("--model", help="Budget for specific model")
@click.option("--alert-at", type=float, default=0.8, help="Alert threshold (0.0-1.0)")
@click.option("--hard-limit", is_flag=True, help="Enforce hard limit")
def costs_set_budget(amount, name, period, project, model, alert_at, hard_limit):
    """Set a spending budget"""
    from llm.cost_tracking import CostTracker
    
    category = "global"
    category_value = None
    
    if project:
        category = "project"
        category_value = project
    elif model:
        category = "model"
        category_value = model
    
    tracker = CostTracker()
    budget_id = tracker.set_budget(
        name=name,
        amount=amount,
        period=period,
        category=category,
        category_value=category_value,
        alert_threshold=alert_at,
        hard_limit=hard_limit
    )
    
    limit_type = "hard limit" if hard_limit else "soft limit"
    click.echo(f"Budget '{name}' set: ${amount:.2f}/{period} ({limit_type})")
    if category != "global":
        click.echo(f"  Scope: {category} = {category_value}")


@costs_group.command(name="budget-status")
@click.argument("name", default="default")
def costs_budget_status(name):
    """Check budget status"""
    from llm.cost_tracking import CostTracker
    
    tracker = CostTracker()
    status = tracker.check_budget_status(name)
    
    if not status:
        raise click.ClickException(f"Budget '{name}' not found")
    
    click.echo(f"\nBudget Status: {name}")
    click.echo("=" * 60)
    click.echo(f"Period:       {status['period']}")
    click.echo(f"Budget:       ${status['amount']:.2f}")
    click.echo(f"Spent:        ${status['spent']:.2f} ({status['percentage']:.1f}%)")
    click.echo(f"Remaining:    ${status['remaining']:.2f}")
    click.echo(f"Status:       {status['status'].upper()}")
    
    if status['hard_limit'] and status['percentage'] >= 100:
        click.echo("\n⚠️  HARD LIMIT REACHED - Further spending blocked")
    elif status['status'] == 'critical':
        click.echo("\n⚠️  WARNING: Approaching budget limit")


@costs_group.command(name="list-budgets")
@click.option("--all", "show_all", is_flag=True, help="Show inactive budgets too")
def costs_list_budgets(show_all):
    """List all budgets"""
    from llm.cost_tracking import CostTracker
    
    tracker = CostTracker()
    budgets = tracker.get_budgets(active_only=not show_all)
    
    if not budgets:
        click.echo("No budgets set")
        return
    
    click.echo(f"\nBudgets ({len(budgets)} total)\n")
    click.echo(f"{'Name':<15} {'Amount':<12} {'Period':<10} {'Category':<15} {'Hard Limit'}")
    click.echo("=" * 70)
    
    for budget in budgets:
        hard_limit = "Yes" if budget['hard_limit'] else "No"
        category = budget['category']
        if budget['category_value']:
            category += f":{budget['category_value']}"
        click.echo(f"{budget['name']:<15} ${budget['amount']:<11.2f} {budget['period']:<10} {category:<15} {hard_limit}")


@costs_group.command(name="delete-budget")
@click.argument("name")
@click.option("--force", is_flag=True, help="Don't ask for confirmation")
def costs_delete_budget(name, force):
    """Delete a budget"""
    from llm.cost_tracking import CostTracker
    
    if not force:
        if not click.confirm(f"Delete budget '{name}'?"):
            return
    
    tracker = CostTracker()
    deleted = tracker.delete_budget(name)
    
    if deleted:
        click.echo(f"Budget '{name}' deleted")
    else:
        raise click.ClickException(f"Budget '{name}' not found")


@costs_group.command(name="report")
@click.option("--month", help="Specific month (YYYY-MM)")
@click.option("--from-date", "from_date", help="Start date (YYYY-MM-DD)")
@click.option("--to-date", "to_date", help="End date (YYYY-MM-DD)")
@click.option("--export", "export_file", type=click.File('w'), help="Export to file (JSON)")
def costs_report(month, from_date, to_date, export_file):
    """Generate cost report"""
    from llm.cost_tracking import CostTracker
    import json
    
    tracker = CostTracker()
    
    if month:
        from_date = f"{month}-01"
        # Calculate last day of month
        import calendar
        year, mon = map(int, month.split('-'))
        last_day = calendar.monthrange(year, mon)[1]
        to_date = f"{month}-{last_day:02d}"
    
    spending = tracker.get_spending(from_date=from_date, to_date=to_date)
    
    if export_file:
        json.dump(spending, export_file, indent=2)
        click.echo(f"Report exported to {export_file.name}", err=True)
    else:
        click.echo(f"\nCost Report")
        click.echo("=" * 60)
        click.echo(f"Period:        {spending['start_date']} to {spending['end_date']}")
        click.echo(f"Total Cost:    ${spending['total_cost']:.2f}")
        click.echo(f"Total Prompts: {spending['total_prompts']:,}")
        click.echo(f"Total Tokens:  {spending['total_tokens']:,}")
        
        if spending['by_model']:
            click.echo(f"\nBy Model:")
            click.echo("-" * 60)
            for model, stats in sorted(spending['by_model'].items(), key=lambda x: x[1]['cost'], reverse=True):
                pct = (stats['cost'] / spending['total_cost'] * 100) if spending['total_cost'] > 0 else 0
                click.echo(f"  {model:<25} ${stats['cost']:>8.2f} ({pct:>5.1f}%)  {stats['prompts']:>6} prompts")


# Model Comparison Commands
@cli.group(name="compare")
def compare_group():
    """Compare responses from multiple models"""
    pass


@compare_group.command(name="run")
@click.argument("prompt")
@click.option("-m", "--model", "models", multiple=True, required=True, help="Models to compare (repeat for each)")
@click.option("-s", "--system", help="System prompt")
@click.option("--save", is_flag=True, help="Save comparison")
@click.option("--no-metrics", is_flag=True, help="Don't show metrics")
def compare_run(prompt, models, system, save, no_metrics):
    """Compare the same prompt across multiple models"""
    from llm.model_comparison import ModelComparison
    
    if len(models) < 2:
        raise click.ClickException("Please specify at least 2 models to compare")
    
    comparator = ModelComparison()
    
    click.echo(f"Comparing {len(models)} models...", err=True)
    comparison = comparator.compare(
        prompt=prompt,
        models=list(models),
        system=system,
        save=save
    )
    
    output = comparator.format_comparison_text(comparison, show_metrics=not no_metrics)
    click.echo(output)
    
    if save:
        click.echo(f"\nComparison saved with ID: {comparison['id']}", err=True)


@compare_group.command(name="list")
@click.option("--limit", type=int, default=10, help="Number of comparisons to show")
def compare_list(limit):
    """List recent comparisons"""
    from llm.model_comparison import ModelComparison
    
    comparator = ModelComparison()
    comparisons = comparator.list_comparisons(limit=limit)
    
    if not comparisons:
        click.echo("No comparisons found")
        return
    
    click.echo(f"\nRecent Comparisons ({len(comparisons)})\n")
    click.echo(f"{'ID':<10} {'Date':<20} {'Models':<40} {'Prompt':<30}")
    click.echo("=" * 105)
    
    for comp in comparisons:
        models_str = ", ".join(comp['models'])[:38]
        prompt_str = comp['prompt'][:28]
        date_str = comp['created_at'][:19]
        click.echo(f"{comp['id'][:8]:<10} {date_str:<20} {models_str:<40} {prompt_str:<30}")


@compare_group.command(name="show")
@click.argument("comparison_id")
@click.option("--no-metrics", is_flag=True, help="Don't show metrics")
def compare_show(comparison_id, no_metrics):
    """Show a saved comparison"""
    from llm.model_comparison import ModelComparison
    
    comparator = ModelComparison()
    comparison = comparator.get_comparison(comparison_id)
    
    if not comparison:
        raise click.ClickException(f"Comparison '{comparison_id}' not found")
    
    output = comparator.format_comparison_text(comparison, show_metrics=not no_metrics)
    click.echo(output)


@compare_group.command(name="best")
@click.argument("comparison_id")
@click.option("--criteria", type=click.Choice(["cost", "time", "length"]), default="cost")
def compare_best(comparison_id, criteria):
    """Show the best model from a comparison"""
    from llm.model_comparison import ModelComparison
    
    comparator = ModelComparison()
    comparison = comparator.get_comparison(comparison_id)
    
    if not comparison:
        raise click.ClickException(f"Comparison '{comparison_id}' not found")
    
    best_model = comparator.get_best_model(comparison, criteria=criteria)
    
    if best_model:
        click.echo(f"Best model by {criteria}: {best_model}")
    else:
        click.echo("No successful responses to compare")


# Batch Processing Commands
@cli.group(name="batch")
def batch_group():
    """Process multiple prompts from files"""
    pass


@batch_group.command(name="run")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("-m", "--model", default=None, help="Model to use")
@click.option("--template", help="Prompt template with {variable} placeholders")
@click.option("-s", "--system", help="System prompt")
@click.option("-o", "--output", "output_file", type=click.Path(), help="Output file")
@click.option("--rate-limit", type=int, help="Maximum prompts per minute")
@click.option("--max-prompts", type=int, help="Maximum number of prompts to process")
def batch_run(input_file, model, template, system, output_file, rate_limit, max_prompts):
    """Process prompts from a file"""
    from llm.batch_processing import BatchProcessor
    from llm import get_default_model
    from pathlib import Path
    
    if not model:
        default_model = get_default_model()
        if not default_model:
            raise click.ClickException("No model specified and no default model set")
        # get_default_model() returns a string ID, not a model object
        model = default_model
    
    processor = BatchProcessor()
    
    click.echo(f"Processing batch from {input_file}...", err=True)
    click.echo(f"Model: {model}", err=True)
    
    batch_id = processor.process_batch(
        input_file=Path(input_file),
        model_name=model,
        template=template,
        system=system,
        output_file=Path(output_file) if output_file else None,
        rate_limit=rate_limit,
        max_prompts=max_prompts
    )
    
    click.echo(f"\nBatch processing completed!", err=True)
    click.echo(f"Batch ID: {batch_id}", err=True)
    
    status = processor.get_batch_status(batch_id)
    click.echo(f"Total: {status['total_prompts']}, "
               f"Completed: {status['completed_prompts']}, "
               f"Failed: {status['failed_prompts']}", err=True)
    
    if output_file:
        click.echo(f"Results saved to: {output_file}", err=True)


@batch_group.command(name="list")
@click.option("--limit", type=int, default=10, help="Number of batches to show")
def batch_list(limit):
    """List recent batch runs"""
    from llm.batch_processing import BatchProcessor
    
    processor = BatchProcessor()
    batches = processor.list_batches(limit=limit)
    
    if not batches:
        click.echo("No batch runs found")
        return
    
    click.echo(f"\nBatch Runs ({len(batches)})\n")
    click.echo(f"{'ID':<10} {'Date':<20} {'Model':<15} {'Total':<8} {'Done':<8} {'Status':<10}")
    click.echo("=" * 80)
    
    for batch in batches:
        date_str = batch['created_at'][:19]
        status_str = batch['status']
        click.echo(f"{batch['id'][:8]:<10} {date_str:<20} {batch['model']:<15} "
                   f"{batch['total_prompts']:<8} {batch['completed_prompts']:<8} {status_str:<10}")


@batch_group.command(name="status")
@click.argument("batch_id")
def batch_status(batch_id):
    """Show status of a batch run"""
    from llm.batch_processing import BatchProcessor
    
    processor = BatchProcessor()
    status = processor.get_batch_status(batch_id)
    
    if not status:
        raise click.ClickException(f"Batch '{batch_id}' not found")
    
    click.echo(f"\nBatch Status: {batch_id}")
    click.echo("=" * 60)
    click.echo(f"Status:       {status['status']}")
    click.echo(f"Model:        {status['model']}")
    click.echo(f"Input File:   {status['input_file']}")
    if status['output_file']:
        click.echo(f"Output File:  {status['output_file']}")
    click.echo(f"Total:        {status['total_prompts']}")
    click.echo(f"Completed:    {status['completed_prompts']}")
    click.echo(f"Failed:       {status['failed_prompts']}")
    
    if status['total_prompts'] > 0:
        pct = (status['completed_prompts'] / status['total_prompts']) * 100
        click.echo(f"Progress:     {pct:.1f}%")
    
    click.echo(f"Created:      {status['created_at']}")
    if status['completed_at']:
        click.echo(f"Completed:    {status['completed_at']}")


@cli.group(name="export")
def export_group():
    """Export conversations, comparisons, and batch results"""
    pass


@export_group.command(name="conversation")
@click.argument("conversation_id")
@click.option(
    "--format",
    type=click.Choice(["html", "markdown", "json", "text"]),
    default="markdown",
    help="Output format"
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file path"
)
@click.option(
    "--no-system",
    is_flag=True,
    help="Exclude system prompts from export"
)
@click.option(
    "--template",
    type=click.Path(exists=True),
    help="Custom HTML template file"
)
def export_conversation_cmd(conversation_id, format, output, no_system, template):
    """Export a conversation to various formats"""
    from llm.export_manager import ExportManager

    manager = ExportManager()

    try:
        template_content = None
        if template:
            with open(template, 'r') as f:
                template_content = f.read()

        result = manager.export_conversation(
            conversation_id=conversation_id,
            output_format=format,
            output_file=output,
            template=template_content,
            include_system=not no_system
        )

        if output:
            click.echo(f"Conversation exported to: {result}")
        else:
            click.echo(result)

    except ValueError as e:
        raise click.ClickException(str(e))
    except Exception as e:
        raise click.ClickException(f"Export failed: {str(e)}")


@export_group.command(name="comparison")
@click.argument("comparison_id")
@click.option(
    "--format",
    type=click.Choice(["html", "markdown", "json"]),
    default="markdown",
    help="Output format"
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file path"
)
@click.option(
    "--template",
    type=click.Path(exists=True),
    help="Custom HTML template file"
)
def export_comparison_cmd(comparison_id, format, output, template):
    """Export a model comparison to various formats"""
    from llm.export_manager import ExportManager

    manager = ExportManager()

    try:
        template_content = None
        if template:
            with open(template, 'r') as f:
                template_content = f.read()

        result = manager.export_comparison(
            comparison_id=comparison_id,
            output_format=format,
            output_file=output,
            template=template_content
        )

        if output:
            click.echo(f"Comparison exported to: {result}")
        else:
            click.echo(result)

    except ValueError as e:
        raise click.ClickException(str(e))
    except Exception as e:
        raise click.ClickException(f"Export failed: {str(e)}")


@export_group.command(name="batch")
@click.argument("batch_id")
@click.option(
    "--format",
    type=click.Choice(["csv", "json"]),
    default="csv",
    help="Output format"
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    required=True,
    help="Output file path"
)
def export_batch_cmd(batch_id, format, output):
    """Export batch results to CSV or JSON"""
    from llm.export_manager import ExportManager

    manager = ExportManager()

    try:
        result = manager.export_batch(
            batch_id=batch_id,
            output_format=format,
            output_file=output
        )

        click.echo(f"Batch results exported to: {result}")

    except ValueError as e:
        raise click.ClickException(str(e))
    except Exception as e:
        raise click.ClickException(f"Export failed: {str(e)}")


@cli.group(name="branch")
def branch_group():
    """Manage conversation branches"""
    pass


@branch_group.command(name="create")
@click.argument("branch_name")
@click.option(
    "--conversation",
    "-c",
    help="Conversation ID (uses current if not specified)"
)
@click.option(
    "--from-message",
    "-f",
    type=int,
    help="Branch from message number"
)
@click.option(
    "--description",
    "-d",
    help="Branch description"
)
@click.option(
    "--parent",
    "-p",
    help="Parent branch name"
)
def branch_create_cmd(branch_name, conversation, from_message, description, parent):
    """Create a new branch"""
    from llm.branch_manager import BranchManager

    if not conversation:
        raise click.ClickException("--conversation is required")

    manager = BranchManager()

    try:
        branch_id = manager.create_branch(
            conversation_id=conversation,
            branch_name=branch_name,
            from_message=from_message,
            description=description,
            parent_branch=parent
        )

        click.echo(f"Branch '{branch_name}' created: {branch_id}")

    except ValueError as e:
        raise click.ClickException(str(e))


@branch_group.command(name="list")
@click.option(
    "--conversation",
    "-c",
    required=True,
    help="Conversation ID"
)
@click.option(
    "--include-archived",
    is_flag=True,
    help="Include archived branches"
)
def branch_list_cmd(conversation, include_archived):
    """List all branches"""
    from llm.branch_manager import BranchManager

    manager = BranchManager()
    branches = manager.list_branches(conversation, include_inactive=include_archived)

    if not branches:
        click.echo("No branches found")
        return

    click.echo(f"\nBranches for conversation {conversation}:")
    click.echo("=" * 70)

    for branch in branches:
        status = "" if branch["active"] else " [ARCHIVED]"
        click.echo(f"\n{branch['branch_name']}{status}")
        click.echo(f"  Messages: {branch['message_count']}")
        click.echo(f"  Created:  {branch['created_at']}")
        if branch['description']:
            click.echo(f"  Description: {branch['description']}")


@branch_group.command(name="tree")
@click.option(
    "--conversation",
    "-c",
    required=True,
    help="Conversation ID"
)
@click.option(
    "--format",
    type=click.Choice(["ascii", "json"]),
    default="ascii",
    help="Output format"
)
def branch_tree_cmd(conversation, format):
    """Visualize branch tree"""
    from llm.tree_navigator import TreeNavigator

    navigator = TreeNavigator()
    output = navigator.visualize_tree(conversation, format=format)
    click.echo(output)


@branch_group.command(name="compare")
@click.argument("branch1")
@click.argument("branch2")
@click.option(
    "--conversation",
    "-c",
    required=True,
    help="Conversation ID"
)
def branch_compare_cmd(branch1, branch2, conversation):
    """Compare two branches"""
    from llm.tree_navigator import TreeNavigator

    navigator = TreeNavigator()

    try:
        comparison = navigator.compare_branches(conversation, branch1, branch2)

        click.echo("\nBranch Comparison")
        click.echo("=" * 70)
        click.echo(f"\nBranch 1: {comparison['branch1']['name']}")
        click.echo(f"  Total messages: {comparison['branch1']['total_messages']}")
        click.echo(f"  Unique messages: {comparison['branch1']['unique_messages']}")

        click.echo(f"\nBranch 2: {comparison['branch2']['name']}")
        click.echo(f"  Total messages: {comparison['branch2']['total_messages']}")
        click.echo(f"  Unique messages: {comparison['branch2']['unique_messages']}")

        click.echo(f"\nCommon messages: {comparison['common']['messages']}")
        click.echo(f"Divergence point: Message #{comparison['common']['divergence_point']}")

        if comparison['common_ancestor']:
            click.echo(f"Common ancestor: {comparison['common_ancestor']}")

    except ValueError as e:
        raise click.ClickException(str(e))


@branch_group.command(name="rename")
@click.argument("old_name")
@click.argument("new_name")
@click.option(
    "--conversation",
    "-c",
    required=True,
    help="Conversation ID"
)
def branch_rename_cmd(old_name, new_name, conversation):
    """Rename a branch"""
    from llm.branch_manager import BranchManager

    manager = BranchManager()
    success = manager.rename_branch(conversation, old_name, new_name)

    if success:
        click.echo(f"Branch renamed from '{old_name}' to '{new_name}'")
    else:
        raise click.ClickException(f"Failed to rename branch (may already exist)")


@branch_group.command(name="delete")
@click.argument("branch_name")
@click.option(
    "--conversation",
    "-c",
    required=True,
    help="Conversation ID"
)
@click.option(
    "--force",
    is_flag=True,
    help="Delete branch and all children"
)
def branch_delete_cmd(branch_name, conversation, force):
    """Delete a branch"""
    from llm.branch_manager import BranchManager

    manager = BranchManager()

    try:
        success = manager.delete_branch(conversation, branch_name, force=force)

        if success:
            click.echo(f"Branch '{branch_name}' deleted")
        else:
            raise click.ClickException(f"Branch '{branch_name}' not found")

    except ValueError as e:
        raise click.ClickException(str(e))


@branch_group.command(name="archive")
@click.argument("branch_name")
@click.option(
    "--conversation",
    "-c",
    required=True,
    help="Conversation ID"
)
def branch_archive_cmd(branch_name, conversation):
    """Archive a branch"""
    from llm.branch_manager import BranchManager

    manager = BranchManager()
    success = manager.archive_branch(conversation, branch_name)

    if success:
        click.echo(f"Branch '{branch_name}' archived")
    else:
        raise click.ClickException(f"Branch '{branch_name}' not found")


@cli.group(name="context")
def context_group():
    """Manage conversation context and token limits"""
    pass


@context_group.command(name="status")
@click.option("--conversation", "-c", required=True, help="Conversation ID")
def context_status_cmd(conversation):
    """Show context status"""
    from llm.context_manager import ContextManager

    manager = ContextManager()
    status = manager.get_status(conversation)

    click.echo(f"\nContext Status: {conversation}")
    click.echo("=" * 60)
    click.echo(f"Max tokens:       {status['max_tokens']}")
    click.echo(f"Strategy:         {status['strategy']}")
    click.echo(f"Auto-summarize:   {status['auto_summarize']}")
    click.echo(f"Current messages: {status['current_messages']}")
    click.echo(f"Estimated tokens: {status['estimated_tokens']}")
    click.echo(f"Usage:            {status['percentage_used']:.1f}%")


@context_group.command(name="set-limit")
@click.argument("max_tokens", type=int)
@click.option("--conversation", "-c", required=True, help="Conversation ID")
def context_set_limit_cmd(max_tokens, conversation):
    """Set token limit"""
    from llm.context_manager import ContextManager

    manager = ContextManager()
    manager.set_limit(conversation, max_tokens)
    click.echo(f"Token limit set to {max_tokens}")


@context_group.command(name="set-strategy")
@click.argument("strategy", type=click.Choice(["sliding_window", "summarize_old", "keep_important"]))
@click.option("--conversation", "-c", required=True, help="Conversation ID")
def context_set_strategy_cmd(strategy, conversation):
    """Set context management strategy"""
    from llm.context_manager import ContextManager

    manager = ContextManager()
    manager.set_strategy(conversation, strategy)
    click.echo(f"Strategy set to '{strategy}'")


@context_group.command(name="summarize")
@click.option("--conversation", "-c", required=True, help="Conversation ID")
@click.option("--keep", type=int, default=5, help="Number of recent messages to keep")
def context_summarize_cmd(conversation, keep):
    """Summarize old messages"""
    from llm.context_manager import ContextManager

    manager = ContextManager()
    summary = manager.summarize(conversation, keep_recent=keep)
    click.echo(f"\nSummary:\n{summary}")


@cli.group(name="benchmark")
def benchmark_group():
    """Run and manage model benchmarks"""
    pass


@benchmark_group.command(name="create")
@click.argument("name")
@click.option("--from-file", type=click.Path(exists=True), help="Load test cases from JSON file")
@click.option("--description", help="Benchmark description")
def benchmark_create_cmd(name, from_file, description):
    """Create a new benchmark"""
    from llm.benchmark_manager import BenchmarkManager
    import json

    if not from_file:
        raise click.ClickException("--from-file is required")

    with open(from_file, 'r') as f:
        test_cases = json.load(f)

    manager = BenchmarkManager()
    benchmark_id = manager.create_benchmark(name, test_cases, description)

    click.echo(f"Benchmark '{name}' created: {benchmark_id}")


@benchmark_group.command(name="run")
@click.argument("benchmark_name")
@click.option("-m", "--model", "models", multiple=True, required=True, help="Models to benchmark")
def benchmark_run_cmd(benchmark_name, models):
    """Run a benchmark"""
    from llm.benchmark_manager import BenchmarkManager

    manager = BenchmarkManager()

    click.echo(f"Running benchmark '{benchmark_name}' on {len(models)} models...")

    run_id = manager.run_benchmark(benchmark_name, list(models))
    run = manager.get_run(run_id)

    click.echo(f"\nBenchmark Results:")
    click.echo("=" * 70)

    for model, scores in run["scores"].items():
        click.echo(f"\n{model}:")
        if "error" in scores:
            click.echo(f"  Error: {scores['error']}")
        else:
            click.echo(f"  Accuracy: {scores['accuracy']*100:.1f}%")
            click.echo(f"  Avg Time: {scores['avg_time']:.2f}s")
            click.echo(f"  Tests:    {scores['total_tests']}")


@benchmark_group.command(name="list")
def benchmark_list_cmd():
    """List all benchmarks"""
    from llm.benchmark_manager import BenchmarkManager

    manager = BenchmarkManager()
    benchmarks = manager.list_benchmarks()

    if not benchmarks:
        click.echo("No benchmarks found")
        return

    click.echo("\nAvailable Benchmarks:")
    click.echo("=" * 70)

    for b in benchmarks:
        click.echo(f"\n{b['name']}")
        if b['description']:
            click.echo(f"  {b['description']}")
        click.echo(f"  Created: {b['created_at']}")


@cli.group(name="optimize")
def optimize_group():
    """Optimize prompts for better results"""
    pass


@optimize_group.command(name="prompt")
@click.argument("prompt")
@click.option("--strategy", type=click.Choice(["auto", "expand", "simplify", "clarify"]), default="auto")
@click.option("--model", default="gpt-4o", help="Model to use for optimization")
def optimize_prompt_cmd(prompt, strategy, model):
    """Optimize a prompt"""
    from llm.prompt_optimizer import PromptOptimizer

    optimizer = PromptOptimizer()
    result = optimizer.optimize(prompt, strategy, model)

    if "error" in result:
        raise click.ClickException(result["error"])

    click.echo("\nPrompt Optimization")
    click.echo("=" * 70)
    click.echo(f"\nOriginal:\n{result['original']}")
    click.echo(f"\nOptimized ({result['strategy']}):\n{result['optimized']}")
    click.echo(f"\nImprovement: {result['improvement']}")


@optimize_group.command(name="test")
@click.argument("prompt")
@click.option("--variants", type=int, default=3, help="Number of variants to generate")
@click.option("--model", default="gpt-4o", help="Model to use")
def optimize_test_cmd(prompt, variants, model):
    """Test multiple prompt variants"""
    from llm.prompt_optimizer import PromptOptimizer

    optimizer = PromptOptimizer()
    results = optimizer.test_variants(prompt, variants, model)

    click.echo("\nPrompt Variants:")
    click.echo("=" * 70)

    for r in results:
        click.echo(f"\nVariant #{r['number']}:")
        if r.get('variant'):
            click.echo(f"{r['variant']}")
            if "result" in r and "error" not in r["result"]:
                click.echo(f"Response length: {r['result'].get('length', 0)} chars")
        else:
            click.echo(f"Error: {r.get('error', 'Unknown')}")


@cli.group(name="schedule")
def schedule_group():
    """Schedule prompts to run automatically"""
    pass


@schedule_group.command(name="add")
@click.argument("prompt")
@click.option("--model", default="gpt-4o", help="Model to use")
@click.option("--at", help="Run once at specific time (ISO format)")
@click.option("--cron", help="Cron expression for recurring schedule")
@click.option("--name", help="Job name")
@click.option("--system", help="System prompt")
def schedule_add_cmd(prompt, model, at, cron, name, system):
    """Add a scheduled job"""
    from llm.scheduler import Scheduler

    if not at and not cron:
        raise click.ClickException("Either --at or --cron is required")

    schedule_type = "once" if at else "cron"
    schedule_value = at or cron

    scheduler = Scheduler()
    job_id = scheduler.add_job(
        prompt=prompt,
        model=model,
        schedule_type=schedule_type,
        schedule_value=schedule_value,
        name=name,
        system_prompt=system
    )

    click.echo(f"Job scheduled: {job_id}")


@schedule_group.command(name="list")
def schedule_list_cmd():
    """List scheduled jobs"""
    from llm.scheduler import Scheduler

    scheduler = Scheduler()
    jobs = scheduler.list_jobs()

    if not jobs:
        click.echo("No scheduled jobs")
        return

    click.echo("\nScheduled Jobs:")
    click.echo("=" * 70)

    for job in jobs:
        click.echo(f"\n{job['name'] or job['id']}")
        click.echo(f"  Model:     {job['model']}")
        click.echo(f"  Type:      {job['schedule_type']}")
        click.echo(f"  Schedule:  {job['schedule_value']}")
        if job['last_run']:
            click.echo(f"  Last run:  {job['last_run']}")


@schedule_group.command(name="run")
@click.argument("job_id")
def schedule_run_cmd(job_id):
    """Run a job immediately"""
    from llm.scheduler import Scheduler

    scheduler = Scheduler()
    run_id = scheduler.run_job_now(job_id)
    click.echo(f"Job executed: {run_id}")


@schedule_group.command(name="delete")
@click.argument("job_id")
def schedule_delete_cmd(job_id):
    """Delete a scheduled job"""
    from llm.scheduler import Scheduler

    scheduler = Scheduler()
    success = scheduler.delete_job(job_id)

    if success:
        click.echo(f"Job deleted: {job_id}")
    else:
        raise click.ClickException(f"Job not found: {job_id}")
