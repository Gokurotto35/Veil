import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from pengu.communication.message_handler import MessageHandler

# Every message type the bridge accepts and the handler it reaches. Pinned
# from the if/elif chain in MessageHandler._route so that reshaping the
# router (dispatch table, split by domain) cannot drop or misroute a type
ROUTES = {
    "chroma-log": "_handle_chroma_log",
    "plugin-log": "_handle_chroma_log",
    "request-local-preview": "_handle_request_local_preview",
    "request-local-asset": "_handle_request_local_asset",
    "chroma-selection": "_handle_chroma_selection",
    "dice-button-click": "_handle_dice_button_click",
    "settings-request": "_handle_settings_request",
    "path-validate": "_handle_path_validate",
    "open-mods-folder": "_handle_open_mods_folder",
    "request-skin-mods": "_handle_request_skin_mods",
    "request-manage-categories": "_handle_request_manage_categories",
    "request-manage-champion-mods": "_handle_request_manage_champion_mods",
    "request-manage-category-mods": "_handle_request_manage_category_mods",
    "request-maps": "_handle_request_maps",
    "request-fonts": "_handle_request_fonts",
    "request-announcers": "_handle_request_announcers",
    "request-category-mods": "_handle_request_category_mods",
    "select-skin-mod": "_handle_select_skin_mod",
    "select-map": "_handle_select_map",
    "select-font": "_handle_select_font",
    "select-announcer": "_handle_select_announcer",
    "select-other": "_handle_select_other",
    "open-logs-folder": "_handle_open_logs_folder",
    "diagnostics-request": "_handle_diagnostics_request",
    "diagnostics-clear": "_handle_diagnostics_clear",
    "stop-injection": "_handle_stop_injection",
    "diagnostics-delete": "_handle_diagnostics_delete",
    "diagnostics-clear-category": "_handle_diagnostics_clear_category",
    "diagnostics-clear-tracker": "_handle_diagnostics_clear_tracker",
    "diagnostics-apply-recommended": "_handle_diagnostics_apply_recommended",
    "open-pengu-loader-ui": "_handle_open_pengu_loader_ui",
    "settings-save": "_handle_settings_save",
    "language-save": "_handle_language_save",
    "add-custom-mods-category-selected": "_handle_add_custom_mods_category_selected",
    "add-custom-mods-champion-selected": "_handle_add_custom_mods_champion_selected",
    "add-custom-mods-skin-selected": "_handle_add_custom_mods_skin_selected",
    "find-match-hover": "_handle_find_match_hover",
    "dismiss-custom-mod": "_handle_dismiss_custom_mod",
    "delete-champion-mod": "_handle_delete_champion_mod",
    "delete-category-mod": "_handle_delete_category_mod",
    "rename-champion-mod": "_handle_rename_champion_mod",
    "rename-category-mod": "_handle_rename_category_mod",
    "dismiss-historic": "_handle_dismiss_historic",
    "party-enable": "_handle_party_enable",
    "party-disable": "_handle_party_disable",
    "party-add-peer": "_handle_party_add_peer",
    "party-remove-peer": "_handle_party_remove_peer",
    "party-get-state": "_handle_party_get_state",
}

HANDLER_NAMES = sorted(name for name in vars(MessageHandler) if name.startswith("_handle_"))


class MessageRoutingTests(unittest.TestCase):

    def setUp(self):
        self.handler = MessageHandler.__new__(MessageHandler)
        self.handler.mod_storage = MagicMock(CATEGORY_OTHERS="others")
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.mocks = {
            name: stack.enter_context(patch.object(MessageHandler, name))
            for name in HANDLER_NAMES
        }

    def called(self):
        return {name: mock.call_args for name, mock in self.mocks.items() if mock.called}

    def test_each_type_reaches_only_its_handler(self):
        for payload_type, handler_name in ROUTES.items():
            with self.subTest(payload_type):
                for mock in self.mocks.values():
                    mock.reset_mock()
                payload = {"type": payload_type, "value": 1}
                self.handler._route(payload_type, payload)
                self.assertEqual(self.called(), {handler_name: ((payload,), {})})

    def test_a_type_wins_over_a_skin_field(self):
        payload = {"type": "settings-request", "skin": "Star Guardian Ahri"}
        self.handler._route("settings-request", payload)
        self.assertEqual(list(self.called()), ["_handle_settings_request"])

    def test_request_others_asks_for_the_others_category(self):
        self.handler._route("request-others", {"type": "request-others"})
        self.assertEqual(
            self.called(),
            {"_handle_request_category_mods": (({"category": "others"},), {})},
        )

    def test_an_untyped_message_with_a_skin_is_a_skin_detection(self):
        # VEIL-SkinMonitor sends "skin-sync", which only reaches the handler
        # through this fallback
        for payload_type in (None, "unknown-type", "skin-sync"):
            with self.subTest(payload_type):
                for mock in self.mocks.values():
                    mock.reset_mock()
                payload = {"type": payload_type, "skin": "Star Guardian Ahri"}
                self.handler._route(payload_type, payload)
                self.assertEqual(self.called(), {"_handle_skin_detection": ((payload,), {})})

    def test_an_unknown_message_without_a_skin_is_ignored(self):
        for payload in ({"type": "unknown-type"}, {"type": "unknown-type", "skin": ""}, {}):
            with self.subTest(payload):
                self.handler._route(payload.get("type"), payload)
                self.assertEqual(self.called(), {})

    def test_every_handler_is_routed(self):
        routed = set(ROUTES.values()) | {"_handle_skin_detection"}
        self.assertEqual(set(HANDLER_NAMES) - routed, set())


if __name__ == "__main__":
    unittest.main()
