# vim: set expandtab shiftwidth=4 softtabstop=4:
"""Log messages, with the options a reader needs made clickable.

A warning that names an option is only useful if the option can be found, so
messages here link into the bundle's help page through ChimeraX's `cxcmd:`
scheme: clicking the link runs the command. Everything composed from data goes
through `escape` first, since drawing names and colour names end up in these
strings.
"""

from html import escape

HELP_COMMAND = "help 3mf"


def cmd_link(command, text=None):
    """A log link that runs a ChimeraX command when clicked."""
    return '<a href="cxcmd:%s">%s</a>' % (escape(command),
                                          escape(text or command))


def help_link(anchor=None, text=None):
    """Link to this bundle's help page, optionally to a section of it.

    `help 3mf` resolves because ChimeraX derives the page from the command's
    first word; a section needs the page opened by URL, since `help` takes a
    topic rather than a fragment.
    """
    if anchor is None:
        return cmd_link(HELP_COMMAND, text or HELP_COMMAND)
    return cmd_link("open help:user/commands/3mf.html#%s" % anchor,
                    text or HELP_COMMAND)


def warn(session, text, html=False):
    session.logger.warning(text if html else escape(text), is_html=True)


def info(session, text, html=False):
    session.logger.info(text if html else escape(text), is_html=True)


def help_hint(session, lead="More options:"):
    """One trailing pointer at the help page, rather than one per warning."""
    session.logger.info("%s %s" % (escape(lead), help_link()), is_html=True)
