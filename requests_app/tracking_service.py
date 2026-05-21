import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class TrackingMoreTracker:
    """TrackingMore API v4 integration using direct HTTP requests."""
    
    def __init__(self):
        self.api_key = getattr(settings, 'TRACKINGMORE_API_KEY', None)
        self.base_url = "https://api.trackingmore.com/v4"
        self.use_api = bool(self.api_key)
    
    def _get_headers(self):
        return {
            "Content-Type": "application/json",
            "Tracking-Api-Key": self.api_key or ""
        }
    
    def detect_courier(self, tracking_number):
        """Detect which courier a tracking number belongs to."""
        if not self.use_api:
            logger.warning("TrackingMore API key not configured")
            return {"meta": {"code": 400, "message": "API key not configured"}}
        
        try:
            response = requests.post(
                f"{self.base_url}/couriers/detect",
                json={"tracking_number": tracking_number},
                headers=self._get_headers(),
                timeout=30
            )
            return response.json()
        except Exception as e:
            logger.error(f"TrackingMore detect error: {e}")
            return {"meta": {"code": 500, "message": str(e)}}
    
    def create_tracking(self, tracking_number, courier_code, title=None, extra_fields=None):
        """
        Create/import a tracking number to TrackingMore.
        Uses V4 API - creates tracking and gets results in real-time.
        """
        if not self.use_api:
            logger.warning("TrackingMore API key not configured - shipment will not appear on TrackingMore dashboard")
            logger.warning("Add TRACKINGMORE_API_KEY to your environment variables to enable this feature")
            return {"meta": {"code": 202, "message": "API key not configured - local only"}, "data": {}}
        
        try:
            base_data = {
                "tracking_number": tracking_number,
                "courier_code": courier_code
            }
            data = dict(base_data)
            if title:
                data["title"] = title
            if extra_fields:
                data.update(
                    {
                        key: value
                        for key, value in extra_fields.items()
                        if value not in [None, ""]
                    }
                )
            
            logger.info(f"TrackingMore API: Creating tracking for {tracking_number} with courier {courier_code}")
            logger.info(f"TrackingMore API: Request data: {data}")
            logger.info(f"TrackingMore API: Headers: {self._get_headers()}")
            
            response = requests.post(
                f"{self.base_url}/trackings/create",
                json=data,
                headers=self._get_headers(),
                timeout=30
            )
            logger.info(f"TrackingMore API: Response status: {response.status_code}")
            result = response.json()
            logger.info(f"TrackingMore API: Response body: {result}")
            
            meta_code = result.get("meta", {}).get("code")

            # Handle "already exists" as success.
            if meta_code in {409, 4101}:
                logger.info(f"Tracking number {tracking_number} already exists in TrackingMore")
                return {"meta": {"code": 200, "message": "Tracking already exists"}, "data": {}}

            # Some TrackingMore accounts reject optional field names on V4 create.
            # Retry with the minimum accepted payload so the shipment still appears
            # in the TrackingMore dashboard.
            if meta_code == 4130 and data != base_data:
                logger.warning(
                    "TrackingMore rejected optional fields for %s; retrying with minimal payload.",
                    tracking_number,
                )
                response = requests.post(
                    f"{self.base_url}/trackings/create",
                    json=base_data,
                    headers=self._get_headers(),
                    timeout=30
                )
                result = response.json()
                meta_code = result.get("meta", {}).get("code")
                if meta_code in {409, 4101}:
                    logger.info(f"Tracking number {tracking_number} already exists in TrackingMore")
                    return {"meta": {"code": 200, "message": "Tracking already exists"}, "data": {}}
            
            if meta_code == 401:
                logger.error("TrackingMore Authentication Failed!")
                logger.error("Your API key is invalid or has expired")
                logger.error("Visit https://admin.trackingmore.com/ to get a valid API key")
            
            logger.info(f"TrackingMore create response: {result}")
            return result
        except Exception as e:
            logger.error(f"TrackingMore create error: {e}")
            return {"meta": {"code": 500, "message": str(e)}}
    
    def get_tracking(self, courier_code, tracking_number):
        """
        Get tracking results using V4 API.
        """
        if not self.use_api:
            logger.warning("TrackingMore API key not configured")
            return {"meta": {"code": 400, "message": "API key not configured"}}
        
        try:
            params = {
                "tracking_numbers": tracking_number,
                "courier_code": courier_code
            }
            response = requests.get(
                f"{self.base_url}/trackings/get",
                params=params,
                headers=self._get_headers(),
                timeout=30
            )
            return response.json()
        except Exception as e:
            logger.error(f"TrackingMore get error: {e}")
            return {"meta": {"code": 500, "message": str(e)}}
    
    def get_realtime_tracking(self, courier_code, tracking_number):
        """Get realtime tracking results."""
        if not self.use_api:
            return {"meta": {"code": 400, "message": "API key not configured"}}
        
        try:
            response = requests.post(
                f"{self.base_url}/trackings/realtime",
                json={
                    "tracking_number": tracking_number,
                    "carrier_code": courier_code
                },
                headers=self._get_headers(),
                timeout=30
            )
            return response.json()
        except Exception as e:
            logger.error(f"TrackingMore realtime error: {e}")
            return {"meta": {"code": 500, "message": str(e)}}
    
    def get_account_info(self):
        """Get account information."""
        if not self.use_api:
            return {"meta": {"code": 400, "message": "API key not configured"}}
        
        try:
            response = requests.get(
                f"{self.base_url}/trackings/getuserinfo",
                headers=self._get_headers(),
                timeout=30
            )
            return response.json()
        except Exception as e:
            logger.error(f"TrackingMore user info error: {e}")
            return {"meta": {"code": 500, "message": str(e)}}


class LBCTracker:
    """LBC Tracker - uses TrackingMore API v4."""
    
    def __init__(self):
        self.tracking_more = TrackingMoreTracker()
        self.courier_code = "lbcexpress"
    
    def register_lbc_tracking(self, tracking_number, document_request=None):
        """
        Register LBC tracking number with TrackingMore.
        Uses V4 API - creates tracking and gets results in real-time.
        First detects the courier to ensure proper tracking.
        """
        extra_fields = {}
        if document_request is not None:
            try:
                student_name = document_request.get_student_name()
            except Exception:
                student_name = document_request.student.username

            extra_fields = {
                "title": f"{student_name} - {document_request.document_type.name}",
                "customer_name": student_name,
                "customer_email": document_request.student.email,
                "customer_phone": document_request.shipping_phone,
                "order_id": document_request.batch_id or tracking_number,
                "logistics_channel": "LBC",
                "tracking_postal_code": document_request.shipping_zip,
                "tracking_destination_country": "PH",
                "comment": document_request.reason,
                "order_create_time": document_request.created_at.strftime(
                    "%Y/%m/%d %H:%M"
                )
                if document_request.created_at
                else None,
            }

        logger.info(f"Registering LBC tracking: {tracking_number}")
        
        # First, try to detect the courier to ensure we use the correct one
        detected_courier = None
        detect_result = self.tracking_more.detect_courier(tracking_number)
        logger.info(f"Courier detection result: {detect_result}")
        
        if detect_result.get("meta", {}).get("code") == 200:
            data = detect_result.get("data", {})
            if data and len(data) > 0:
                # Get the first detected courier
                detected_courier = data[0].get("courier_code")
                logger.info(f"Detected courier: {detected_courier}")
        
        # Use detected courier or fall back to lbcexpress
        courier_code = detected_courier or self.courier_code
        
        result = self.tracking_more.create_tracking(
            tracking_number=tracking_number,
            courier_code=courier_code,
            title=extra_fields.get("title") or "CATC Student Document Request",
            extra_fields=extra_fields,
        )
        logger.info(f"LBC registration result: {result}")
        return result
    
    def get_status(self, tracking_number):
        """Get tracking status from TrackingMore."""
        logger.info(f"Getting LBC status for: {tracking_number}")
        
        # Try realtime tracking first (more accurate)
        result = self.tracking_more.get_realtime_tracking(self.courier_code, tracking_number)
        logger.info(f"LBC realtime response: {result}")
        
        # If realtime fails, try get tracking
        if result.get("meta", {}).get("code") != 200:
            result = self.tracking_more.get_tracking(self.courier_code, tracking_number)
            logger.info(f"LBC get response: {result}")
        
        if result.get("meta", {}).get("code") in [200, 201]:
            data = result.get("data", {})
            
            # Handle V4 response format - data is the tracking object directly
            if isinstance(data, dict):
                item = data
                
                status = item.get("delivery_status", "Unknown")
                substatus = item.get("substatus", "")
                status_info = item.get("status_info", "")
                latest_event = item.get("latest_event", "")
                latest_checkpoint_time = item.get("latest_checkpoint_time", "")
                
                # Extract origin/destination info
                origin_info = item.get("origin_info", {})
                dest_info = item.get("destination_info", {})
                
                # Build tracking details from checkpoints
                tracking_details = []
                
                # Get checkpoints from origin_info
                if origin_info and "trackinfo" in origin_info:
                    for cp in origin_info["trackinfo"]:
                        tracking_details.append({
                            "status": cp.get("status", ""),
                            "location": cp.get("location", ""),
                            "datetime": cp.get("datetime", ""),
                            "description": cp.get("status_description", ""),
                        })
                
                # Get checkpoints from destination_info
                if dest_info and "trackinfo" in dest_info:
                    for cp in dest_info["trackinfo"]:
                        tracking_details.append({
                            "status": cp.get("status", ""),
                            "location": cp.get("location", ""),
                            "datetime": cp.get("datetime", ""),
                            "description": cp.get("status_description", ""),
                        })
                
                # If no checkpoints, use status_info
                if not tracking_details and status_info:
                    tracking_details.append({
                        "status": status,
                        "location": "",
                        "datetime": latest_checkpoint_time,
                        "description": status_info,
                    })
                
                return {
                    "meta": {"code": 200, "message": "OK"},
                    "data": {
                        "id": item.get("id", ""),
                        "status": status,
                        "substatus": substatus,
                        "tracking_number": tracking_number,
                        "courier_code": item.get("courier_code", ""),
                        "origin": item.get("origin_city", "") or item.get("origin_country", ""),
                        "destination": item.get("destination_city", "") or item.get("destination_country", ""),
                        "last_event": latest_event or status_info,
                        "status_info": status_info,
                        "latest_checkpoint_time": latest_checkpoint_time,
                        "tracking_details": tracking_details,
                        "delivery_status": status,
                        "updating": item.get("updating", True),
                        "transit_time": item.get("transit_time", 0),
                    }
                }
            
            return {"meta": {"code": 404, "message": "Tracking not found"}, "data": {}}
        
        return result
    
    def get_tracking_by_date(self, date_from, date_to):
        """Get tracking info by date range."""
        return {"meta": {"code": 400, "message": "Use get_status instead"}}
    
    def detect_carrier(self, tracking_number):
        """Detect the carrier for a tracking number."""
        return self.tracking_more.detect_courier(tracking_number)
