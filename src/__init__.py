# vim: set expandtab shiftwidth=4 softtabstop=4:
"""Save the current ChimeraX scene as a 3MF file for 3D printing."""

from chimerax.core.toolshed import BundleAPI


class _Save3MFAPI(BundleAPI):

    @staticmethod
    def run_provider(session, name, mgr, **kw):
        from chimerax.save_command import SaverInfo

        class Info(SaverInfo):
            def save(self, session, path, **kw):
                from . import writer3mf
                writer3mf.write_3mf(session, path, **kw)

            @property
            def save_args(self):
                from chimerax.core.commands import ModelsArg, FloatArg
                return {
                    'models': ModelsArg,
                    'scale': FloatArg,
                    'size': FloatArg,
                }

        return Info()


bundle_api = _Save3MFAPI()
