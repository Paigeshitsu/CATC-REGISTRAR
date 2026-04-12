import requests
import json
import logging
from django.conf import settings

# Set up a logger to catch errors without crashing the app
logger = logging.getLogger(__name__)


class LBCTracker:
    def __init__(self):
        # Tracktry API (legacy - kept for backward compatibility)
        # NOTE: In production, move this to environment variable
        self.tracktry_api_key = getattr(settings, 'TRACKTRY_API_KEY', 'xa48ca5i-5fw2-4pao-3z2q-vkj9l1i2lrlf')
        self.tracktry_base_url = "https://api.tracktry.com/v1/trackings"
        
        # LBC CBIP Track and Trace API (new integration)
        self.lbc_base_url = "https://lbcapigateway.lbcapps.com/cbiptrackandtrace/v2"
        self.lbc_api_key = getattr(settings, 'LBC_API_KEY', None)
        self.lbc_subscription_key = getattr(settings, 'LBC_SUBSCRIPTION_KEY', None)
        # Use new LBC API by default
        self.use_lbc_api = bool(self.lbc_api_key and self.lbc_subscription_key)

    def _execute_request(self, method, url, data=None, headers=None, params=None):
        """
        Private helper to handle the actual HTTP communication.
        Includes error handling and timeouts.
        
        Args:
            method: HTTP method (GET, POST)
            url: Full URL to request
            data: Request body data (for POST)
            headers: HTTP headers dictionary
            params: URL query parameters dictionary (for GET requests)
        """
        if headers is None:
            headers = {}
        headers.setdefault("Content-Type", "application/json")
        
        try:
            if method.lower() == "post":
                response = requests.post(url, data=data, headers=headers, timeout=30)
            elif method.lower() == "get":
                response = requests.get(url, headers=headers, params=params, timeout=30)
            else:
                return {"meta": {"code": 400, "message": "Invalid Method"}}

            # Check if the response is actually JSON
            return response.json()
        
        except requests.exceptions.Timeout:
            logger.error("LBC Tracking API timed out.")
            return {"meta": {"code": 408, "message": "Request Timeout"}}
        except requests.exceptions.RequestException as e:
            logger.error(f"LBC Tracking API Error: {e}")
            return {"meta": {"code": 500, "message": str(e)}}
        except Exception as e:
            logger.error(f"Unexpected Error in Tracking Service: {e}")
            return {"meta": {"code": 500, "message": "Unexpected Error"}}

    def _get_lbc_headers(self, date_from=None, date_to=None):
        """
        Generate headers for LBC CBIP Track and Trace API.
        """
        headers = {
            "Content-Type": "application/json",
            "lbcOAkey": self.lbc_api_key or "",
        }
        # Add date parameters to headers if provided
        if date_from:
            headers["date_from"] = date_from if isinstance(date_from, str) else date_from.strftime('%Y-%m-%d')
        if date_to:
            headers["date_to"] = date_to if isinstance(date_to, str) else date_to.strftime('%Y-%m-%d')
        return headers

    def register_lbc_tracking(self, tracking_number):
        """
        Registers a new tracking number with LBC CBIP Track and Trace API.
        This is called when the Registrar marks a document as 'READY'.
        
        Falls back to Tracktry if LBC API credentials are not configured.
        """
        if self.use_lbc_api:
            # Use LBC CBIP Track and Trace API
            # POST /* endpoint (catch-all)
            url = f"{self.lbc_base_url}/*"
            payload = json.dumps({
                "tracking_number": str(tracking_number).strip(),
                "carrier_code": "lbc-express",
                "comment": "CATC Student Document Request"
            })
            headers = self._get_lbc_headers()
            return self._execute_request("post", url, data=payload, headers=headers)
        else:
            # Fallback to Tracktry API (legacy)
            payload = json.dumps({
                "tracking_number": str(tracking_number).strip(),
                "carrier_code": "lbc-express",
                "comment": "CATC Student Document Request"
            })
            headers = {
                "Content-Type": "application/json",
                "Tracking-Api-Key": self.tracktry_api_key
            }
            return self._execute_request("post", self.tracktry_base_url, data=payload, headers=headers)

    def get_status(self, tracking_number, date_from=None, date_to=None):
        """
        Fetches the current location/status of the LBC package.
        Uses LBC CBIP Track and Trace API if configured.
        
        Args:
            tracking_number: The LBC tracking number
            date_from: Optional filter date (start)
            date_to: Optional filter date (end)
        """
        if self.use_lbc_api:
            # Use LBC CBIP Track and Trace API - GET /api/track/cbipV2
            url = f"{self.lbc_base_url}/api/track/cbipV2"
            headers = self._get_lbc_headers(date_from, date_to)
            # Add subscription key as query parameter
            params = {"lbcsubscriptionkey": self.lbc_subscription_key}
            return self._execute_request("get", url, headers=headers, params=params)
        else:
            # Fallback to Tracktry API (legacy)
            url_path = f"{self.tracktry_base_url}/lbc-express/{tracking_number}"
            headers = {
                "Content-Type": "application/json",
                "Tracking-Api-Key": self.tracktry_api_key
            }
            return self._execute_request("get", url_path, headers=headers)

    def get_tracking_by_date(self, date_from, date_to):
        """
        Fetches tracking information for shipments within a date range.
        Uses LBC CBIP Track and Trace API.
        
        Args:
            date_from: Start date (string or date object)
            date_to: End date (string or date object)
        """
        if not self.use_lbc_api:
            return {"meta": {"code": 400, "message": "LBC API credentials not configured"}}
        
        url = f"{self.lbc_base_url}/api/track/cbipV2"
        headers = self._get_lbc_headers(date_from, date_to)
        # Add subscription key as query parameter
        params = {"lbcsubscriptionkey": self.lbc_subscription_key}
        return self._execute_request("get", url, headers=headers, params=params)

    def detect_carrier(self, tracking_number):
        """
        Optional: If you ever use carriers other than LBC.
        Uses Tracktry API (legacy).
        """
        url = f"{self.tracktry_base_url}/carriers/detect"
        payload = json.dumps({"tracking_number": tracking_number})
        headers = {
            "Content-Type": "application/json",
            "Tracking-Api-Key": self.tracktry_api_key
        }
        return self._execute_request("post", url, data=payload, headers=headers)
