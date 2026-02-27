import requests
import json
import logging

# Set up a logger to catch errors without crashing the app
logger = logging.getLogger(__name__)

class LBCTracker:
    def __init__(self):
        # API Key from your Tracktry Account
        self.api_key = "xa48ca5i-5fw2-4pao-3z2q-vkj9l1i2lrlf"
        self.base_url = "https://api.tracktry.com/v1/trackings"

    def _execute_request(self, method, url, data=None):
        """
        Private helper to handle the actual HTTP communication.
        Includes error handling and timeouts.
        """
        headers = {
            "Content-Type": "application/json",
            "Tracking-Api-Key": self.api_key
        }
        
        try:
            if method.lower() == "post":
                response = requests.post(url, data=data, headers=headers, timeout=10)
            elif method.lower() == "get":
                response = requests.get(url, headers=headers, timeout=10)
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

    def register_lbc_tracking(self, tracking_number):
        """
        Registers a new tracking number with Tracktry. 
        This is called when the Registrar marks a document as 'READY'.
        """
        payload = json.dumps({
            "tracking_number": str(tracking_number).strip(),
            "carrier_code": "lbc-express",
            "comment": "CATC Student Document Request"
        })
        
        return self._execute_request("post", self.base_url, data=payload)

    def get_status(self, tracking_number):
        """
        Fetches the current location/status of the LBC package.
        """
        url_path = f"{self.base_url}/lbc-express/{tracking_number}"
        return self._execute_request("get", url_path)

    def detect_carrier(self, tracking_number):
        """
        Optional: If you ever use carriers other than LBC.
        """
        url = f"{self.base_url}/carriers/detect"
        payload = json.dumps({"tracking_number": tracking_number})
        return self._execute_request("post", url, data=payload)