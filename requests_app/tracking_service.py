import requests
import json

class LBCTracker:
    def __init__(self):
        self.api_key = "xa48ca5i-5fw2-4pao-3z2q-vkj9l1i2lrlf"
        self.base_url = "https://api.tracktry.com/v1/trackings" # Standard Tracktry Endpoint

    def tracktry(self, request_data, url_str, method_type):
        headers = {
            "Content-Type": "application/json",
            "Tracking-Api-Key": self.api_key
        }
        
        url = self.base_url
        if method_type == "post":
            response = requests.post(url, data=request_data, headers=headers)
        elif method_type == "codeNumberGet":
            url = f"{self.base_url}{url_str}"
            response = requests.get(url, headers=headers)
        elif method_type == "carriers/detect":
            url = f"{self.base_url}/carriers/detect"
            response = requests.post(url, data=request_data, headers=headers)
        else:
            return None
            
        return response.json()

    def register_lbc_tracking(self, tracking_number):
        """Registers a new tracking number with the API"""
        data = json.dumps({
            "tracking_number": tracking_number,
            "carrier_code": "lbc-express" # Official carrier code for LBC
        })
        return self.tracktry(data, "", "post")

    def get_status(self, tracking_number):
        """Fetches current delivery status"""
        url_path = f"/lbc-express/{tracking_number}"
        return self.tracktry("", url_path, "codeNumberGet")