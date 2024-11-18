import pytest
from http.server import HTTPServer, SimpleHTTPRequestHandler
from threading import Thread
import time
import requests
from edsl import Scenario

# Assuming `Scenario` class is defined somewhere, e.g., from your_module import Scenario


class TestScenario:

    @staticmethod
    def start_test_server():
        """Start a simple HTTP server on localhost."""
        handler = SimpleHTTPRequestHandler
        server = HTTPServer(("localhost", 8000), handler)
        thread = Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()
        return server

    def test_from_url(self):
        server = self.start_test_server()
        try:
            # Give the server a moment to start
            time.sleep(1)

            # Write a temporary file that the server can serve
            test_content = "This is test content for the Scenario class."
            with open("test_file.txt", "w") as f:
                f.write(test_content)

            # URL pointing to our test file
            url = "http://localhost:8000/test_file.txt"

            # Call the from_url method with the local URL
            scenario = Scenario.from_url(url, "test_field")
            # Assert the Scenario object is created with the expected content
            assert scenario["test_field"] == test_content
            assert scenario["url"] == url

        finally:
            # Clean up: Shut down server and delete the temporary file
            server.shutdown()
            server.server_close()
            import os

            os.remove("test_file.txt")
