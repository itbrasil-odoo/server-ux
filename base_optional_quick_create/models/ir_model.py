# Copyright 2016 ACSONE SA/NV (https://acsone.eu)
# Copyright 2016 Akretion (Alexis de Lattre alexis.delattre@akretion.com)
# Copyright 2018 Simone Rubino - Agile Business Group
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import UserError


class IrModel(models.Model):
    _inherit = "ir.model"

    avoid_quick_create = fields.Boolean()

    # brought back these methods `_patch_method` and `_revert_method`
    # From this following PR these methods are removed since
    # there is no any proper use for these methods in odoo.
    # refer this bellow PR for more info.
    # https://github.com/odoo/odoo/pull/110370
    # But since we use this to patch the original_method
    # I added back again.
    @staticmethod
    def _is_quick_create_wrapper(method):
        return getattr(method, "_avoid_quick_create", False)

    @classmethod
    def _patch_method(cls_, model_obj, name, method):
        """Replace the method called ``name`` by ``method`` in the class of
        ``model_obj``; the replaced method stays available as ``method.origin``.

        Idempotent: a class already patched by this module is left alone, so
        repeated calls (write, create, _register_hook after a registry setup)
        never stack wrappers that a single revert could not remove.
        """
        cls = type(model_obj)
        if cls_._is_quick_create_wrapper(getattr(cls, name)):
            return
        origin = getattr(cls, name)
        method.origin = origin
        method._avoid_quick_create = True
        # Copy api attributes from origin so the ORM treats the wrapper correctly
        for attr in ("_api_model", "_api_private", "_readonly"):
            if hasattr(origin, attr) and not hasattr(method, attr):
                setattr(method, attr, getattr(origin, attr))
        setattr(cls, name, method)

    @classmethod
    def _revert_method(cls_, model_obj, name):
        """Restore the method called ``name`` patched by :meth:`_patch_method`,
        however many times it was patched."""
        cls = type(model_obj)
        while cls_._is_quick_create_wrapper(getattr(cls, name)):
            setattr(cls, name, getattr(cls, name).origin)

    def _patch_quick_create(self):
        def _wrap_name_create():
            @api.model
            def wrapper(self, name):
                raise UserError(
                    self.env._(
                        "Can't create %(model)s with name %(name)s quickly.\n"
                        "Please contact your system administrator to disable "
                        "this behaviour.",
                        model=self._name,
                        name=name,
                    )
                )

            return wrapper

        method_name = "name_create"
        for model in self:
            model_obj = self.env.get(model.model)
            if model.avoid_quick_create and model_obj is not None:
                # _wrap_name_create().origin = getattr(model_obj, method_name)
                # setattr(model_obj, method_name, _wrap_name_create())
                self._patch_method(model_obj, method_name, _wrap_name_create())
            elif model_obj is not None:
                self._revert_method(model_obj, method_name)
        return True

    def _register_hook(self):
        models = self.search([], limit=None)
        models._patch_quick_create()
        return super()._register_hook()

    def _unregister_hook(self):
        """Remove the patches installed by _register_hook(): the registry setup
        runs both hooks again on the same classes."""
        for model_cls in self.env.registry.values():
            while self._is_quick_create_wrapper(
                getattr(model_cls, "name_create", None)
            ):
                model_cls.name_create = model_cls.name_create.origin
        return super()._unregister_hook()

    @api.model_create_multi
    def create(self, vals_list):
        ir_models = super().create(vals_list)
        if any("avoid_quick_create" in vals for vals in vals_list):
            ir_models._patch_quick_create()
            self.env.transaction.will_change_registry()
        return ir_models

    def write(self, vals):
        res = super().write(vals)
        if "avoid_quick_create" in vals:
            self._patch_quick_create()
            self.env.transaction.will_change_registry()
        return res
