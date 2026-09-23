# vim: set expandtab shiftwidth=4 softtabstop=4:
"""Save the current ChimeraX scene as a 3MF file for 3D printing."""

from chimerax.core.toolshed import BundleAPI


class _Save3MFAPI(BundleAPI):

    @staticmethod
    def register_command(command_name, logger):
        from . import cmd
        cmd.register_command(command_name, logger)

    @staticmethod
    def run_provider(session, name, mgr, **kw):
        from chimerax.save_command import SaverInfo

        class Info(SaverInfo):
            def save(self, session, path, **kw):
                from . import writer3mf
                writer3mf.write_3mf(session, path, **kw)

            @property
            def save_args(self):
                from chimerax.core.commands import (
                    BoolArg, EnumOf, FloatArg, ModelsArg, PositiveIntArg,
                )
                from .writer3mf import FLAVORS
                return {
                    'models': ModelsArg,
                    'scale': FloatArg,
                    'size': FloatArg,
                    'check': BoolArg,
                    'colors': BoolArg,
                    'max_colors': PositiveIntArg,
                    'flavor': EnumOf(FLAVORS),
                    'paint': BoolArg,
                }

            def save_args_widget(self, session):
                from .gui import SaveOptionsWidget
                return SaveOptionsWidget(session)

            def save_args_string_from_widget(self, widget):
                return widget.options_string()

        return Info()


bundle_api = _Save3MFAPI()
