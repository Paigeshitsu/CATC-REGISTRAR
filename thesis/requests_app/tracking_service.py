import requests
import json
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


class TrackingMoreTracker:
    """TrackingMore API integration for shipment tracking."""
    
    def __init__(self):
        self.api_key = getattr(settings, 'TRACKINGMORE_API_KEY', None)
        self.base_url = "https://api.trackingmore.com/v2"
        self.use_api = bool(self.api_key)
    
    def _get_headers(self):
        return {
            "Content-Type": "application/json",
            "Trackingmore-Api-Key": self.api_key or ""
        }
    
    def _execute_request(self, method, endpoint, data=None, params=None):
        if not self.use_api:
            logger.warning("TrackingMore API key not configured")
            return {"meta": {"code": 400, "message": "API key not configured"}}
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method.upper() == "POST":
                response = requests.post(url, json=data, headers=self._get_headers(), timeout=30)
            elif method.upper() == "GET":
                response = requests.get(url, headers=self._get_headers(), params=params, timeout=30)
            elif method.upper() == "DELETE":
                response = requests.delete(url, headers=self._get_headers(), timeout=30)
            else:
                return {"meta": {"code": 400, "message": "Invalid method"}}
            
            return response.json()
        
        except requests.exceptions.Timeout:
            logger.error("TrackingMore API timed out")
            return {"meta": {"code": 408, "message": "Request timeout"}}
        except requests.exceptions.RequestException as e:
            logger.error(f"TrackingMore API error: {e}")
            return {"meta": {"code": 500, "message": str(e)}}
        except json.JSONDecodeError:
            logger.error("TrackingMore API invalid JSON response")
            return {"meta": {"code": 500, "message": "Invalid JSON response"}}
    
    def detect_courier(self, tracking_number):
        """
        Detect which courier a tracking number belongs to.
        Returns list of possible couriers.
        """
        return self._execute_request(
            "POST", 
            "/carriers/detect",
            data={"tracking_number": tracking_number}
        )
    
    def create_tracking(self, tracking_number, courier_code, title=None):
        """
        Create/import a tracking number to TrackingMore.
        
        Args:
            tracking_number: The tracking number
            courier_code: The courier code (e.g., 'lbc-express' for LBC)
            title: Optional title for the shipment
        """
        data = {
            "tracking_number": tracking_number,
            "carrier_code": courier_code
        }
        if title:
            data["title"] = title
            
        return self._execute_request("POST", "/trackings/post", data=data)
    
    def get_tracking(self, courier_code, tracking_number):
        """
        Get tracking results for a single shipment.
        
        Args:
            courier_code: The courier code (e.g., 'lbc-express')
            tracking_number: The tracking number
        """
        return self._execute_request(
            "GET", 
            f"/trackings/{courier_code}/{tracking_number}"
        )
    
    def get_realtime_tracking(self, courier_code, tracking_number):
        """
        Get realtime tracking results for a single shipment.
        
        Args:
            courier_code: The courier code
            tracking_number: The tracking number
        """
        return self._execute_request(
            "POST",
            "/trackings/realtime",
            data={
                "tracking_number": tracking_number,
                "carrier_code": courier_code
            }
        )
    
    def delete_tracking(self, courier_code, tracking_number):
        """
        Delete a tracking number from TrackingMore.
        """
        return self._execute_request(
            "DELETE",
            f"/trackings/{courier_code}/{tracking_number}"
        )
    
    def get_account_info(self):
        """Get account information and quota."""
        return self._execute_request("GET", "/trackings/getuserinfo")


class LBCTracker:
    """Legacy LBC Tracker - now uses TrackingMore internally."""
    
    def __init__(self):
        self.tracking_more = TrackingMoreTracker()
    
    def register_lbc_tracking(self, tracking_number):
        """
        Register LBC tracking number with TrackingMore.
        LBC Express courier code is 'lbc-express' in TrackingMore.
        """
        return self.tracking_more.create_tracking(
            tracking_number=tracking_number,
            courier_code="lbc-express",
            title="CATC Student Document Request"
        )
    
    def get_status(self, tracking_number):
        """Get tracking status from TrackingMore."""
        result = self.tracking_more.get_tracking("lbc-express", tracking_number)
        
        # Format response to match old interface
        if result.get("meta", {}).get("code") == 200:
            data = result.get("data", {})
            return {
                "meta": {"code": 200, "message": "OK"},
                "data": {
                    "status": data.get("status", "Unknown"),
                    "tracking_number": tracking_number,
                    "origin": data.get("origin", ""),
                    "destination": data.get("destination", ""),
                    "last_event": data.get("last_event", ""),
                    "tracking_details": data.get("tracking_details", [])
                }
            }
        return result
    
    def get_tracking_by_date(self, date_from, date_to):
        """Get tracking info by date range (not directly supported in TrackingMore V2)."""
        return {"meta": {"code": 400, "message": "Use get_tracking instead"}}
    
    def detect_carrier(self, tracking_number):
        """Detect the carrier for a tracking number."""
        return self.tracking_more.detect_courier(tracking_number)