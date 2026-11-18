# vim: set expandtab shiftwidth=4 softtabstop=4:
"""Say on the status line what a long export is doing, and keep the window
alive while it does.

ChimeraX has no progress bar for this, and its log only redraws once the
command has finished, but the status line redraws at once: showing a message
runs Qt's event loop (without user input). That also matters for its own
sake: a window that does not answer for about five seconds is greyed out by
Windows as "Not responding", status line and all. So the long stages call
tick(), which shows the current message again at most twice a second.

Above a million triangles every message also says how big the scene is and
about how long it takes, since ChimeraX does not respond until it is done.
"""

import time

# about 10 s per million triangles, measured on the stress-run scenes
LARGE = 1000000
SECONDS_PER_MILLION = 10.0
TICK_SECONDS = 0.5

_current = None


def tick():
    """Show the current status again if it has been a while. Called from the
    long loops; does nothing outside an export."""
    if _current is not None:
        _current.tick()


class Progress:
    def __init__(self, session):
        global _current
        self.session = session
        self.size_note = ""
        self.message = ""
        self.shown_at = 0.0
        _current = self

    def size(self, triangle_count):
        if triangle_count < LARGE:
            self.size_note = ""
            return
        seconds = triangle_count / 1e6 * SECONDS_PER_MILLION
        if seconds < 45:
            how_long = "under a minute"
        elif seconds < 100:
            how_long = "about a minute"
        else:
            how_long = "a few minutes"
        self.size_note = (" (%.1f million triangles, %s; ChimeraX pauses "
                          "until done)" % (triangle_count / 1e6, how_long))

    def step(self, what):
        self.message = ("Saving 3MF%s: %s\N{HORIZONTAL ELLIPSIS}"
                        % (self.size_note, what))
        self._show()

    def tick(self):
        if self.message and time.time() - self.shown_at >= TICK_SECONDS:
            self._show()

    def _show(self):
        self.session.logger.status(self.message, blank_after=0)
        self.shown_at = time.time()

    def done(self):
        global _current
        if _current is self:
            _current = None
        self.message = ""
        self.session.logger.status("")
