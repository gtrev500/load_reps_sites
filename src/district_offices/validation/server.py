#!/usr/bin/env python3

import os
import json
import time
import threading
import logging
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import tempfile

log = logging.getLogger(__name__)

class ValidationServer:
    """Simple HTTP server for browser-based validation responses."""
    
    def __init__(self, port=0):
        """Initialize validation server.
        
        Args:
            port: Port to listen on (0 = auto-select available port)
        """
        self.port = port
        self.validation_result = None
        self.result_event = threading.Event()
        self.server = None
        self.server_thread = None
        self.temp_dir = tempfile.mkdtemp(prefix="validation_server_")
        
    def start(self):
        """Start the validation server in a background thread."""
        
        class ValidationHandler(SimpleHTTPRequestHandler):
            def __init__(handler_self, *args, **kwargs):
                # Set directory to serve from
                super().__init__(*args, directory=self.temp_dir, **kwargs)
            
            def do_GET(handler_self):
                """Handle GET requests for validation responses."""
                parsed_path = urlparse(handler_self.path)
                
                if parsed_path.path == '/validate':
                    # Parse query parameters
                    query_params = parse_qs(parsed_path.query)
                    decision = query_params.get('decision', [None])[0]
                    bioguide_id = query_params.get('bioguide_id', [None])[0]
                    
                    if decision in ['accept', 'reject']:
                        # Store the validation result
                        self.validation_result = {
                            'decision': decision,
                            'bioguide_id': bioguide_id,
                            'timestamp': time.time()
                        }
                        self.result_event.set()
                        
                        # Send success response
                        handler_self.send_response(200)
                        handler_self.send_header('Content-type', 'text/html')
                        handler_self.send_header('Access-Control-Allow-Origin', '*')
                        handler_self.end_headers()
                        
                        success_html = f"""
                        <!DOCTYPE html>
                        <html>
                        <head>
                            <title>Validation Submitted</title>
                            <style>
                                body {{
                                    font-family: Arial, sans-serif;
                                    display: flex;
                                    justify-content: center;
                                    align-items: center;
                                    height: 100vh;
                                    margin: 0;
                                    background-color: #f0f0f0;
                                }}
                                .message {{
                                    text-align: center;
                                    padding: 2rem;
                                    background: white;
                                    border-radius: 10px;
                                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                                }}
                                .success {{ color: #4CAF50; }}
                                .reject {{ color: #f44336; }}
                            </style>
                        </head>
                        <body>
                            <div class="message">
                                <h2 class="{'success' if decision == 'accept' else 'reject'}">
                                    Validation {'Accepted' if decision == 'accept' else 'Rejected'}
                                </h2>
                                <p>You can close this window now.</p>
                                <p>The terminal will continue processing.</p>
                            </div>
                        </body>
                        </html>
                        """
                        handler_self.wfile.write(success_html.encode())
                    else:
                        handler_self.send_error(400, "Invalid decision parameter")
                else:
                    # Serve files normally
                    super().do_GET()
            
            def log_message(handler_self, format, *args):
                # Suppress request logging
                pass
        
        # Create and start the server
        self.server = HTTPServer(('localhost', self.port), ValidationHandler)
        self.port = self.server.server_port  # Get actual port if auto-selected
        
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()
        
        log.info(f"Validation server started on port {self.port}")
        
    def wait_for_validation(self, timeout=300):
        """Wait for validation response from browser.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            Validation result dict or None if timeout
        """
        if self.result_event.wait(timeout):
            return self.validation_result
        return None
        
    def stop(self):
        """Stop the validation server."""
        if self.server:
            self.server.shutdown()
            self.server_thread.join()
            log.info("Validation server stopped")
            
        # Clean up temp directory
        if os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir)