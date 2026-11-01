import unittest

from app.main import app


class CollaborationRegistrationTests(unittest.TestCase):
    REQUIRED_OPERATIONS = {
        ("/api/collaboration/contacts", "get"),
        ("/api/collaboration/conversations", "get"),
        ("/api/collaboration/conversations", "post"),
        ("/api/collaboration/conversations/{conversation_id}/messages", "get"),
        ("/api/collaboration/conversations/{conversation_id}/messages", "post"),
        ("/api/collaboration/conversations/{conversation_id}/events", "get"),
        ("/api/collaboration/conversations/{conversation_id}/read", "post"),
        ("/api/collaboration/conversations/{conversation_id}/pin", "post"),
        ("/api/collaboration/conversations/{conversation_id}/members", "post"),
        ("/api/collaboration/conversations/{conversation_id}/members/{target_user_id}", "delete"),
        ("/api/collaboration/conversations/{conversation_id}/leave", "post"),
        ("/api/collaboration/conversations/{conversation_id}/title", "patch"),
    }

    def test_all_collaboration_operations_are_registered(self):
        schema = app.openapi()
        registered = {
            (path, method)
            for path, operations in schema["paths"].items()
            if path.startswith("/api/collaboration")
            for method in operations
        }

        self.assertTrue(
            self.REQUIRED_OPERATIONS.issubset(registered),
            f"Missing collaboration operations: {self.REQUIRED_OPERATIONS - registered}",
        )

    def test_every_collaboration_operation_requires_bearer_authentication(self):
        schema = app.openapi()
        for path, method in self.REQUIRED_OPERATIONS:
            with self.subTest(path=path, method=method):
                operation = schema["paths"][path][method]
                self.assertIn(
                    {"HTTPBearer": []},
                    operation.get("security", []),
                    f"{method.upper()} {path} is missing bearer authentication",
                )
