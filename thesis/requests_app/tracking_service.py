import logging
from django.conf import settings

logger = logging.getLogger(__name__)

try:
    import trackingmore
    from trackingmore.exception import TrackingMoreException
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False
    TrackingMoreException = Exception


class TrackingMoreTracker:
    """TrackingMore API integration using official SDK."""
    
    def __init__(self):
        self.api_key = getattr(settings, 'TRACKINGMORE_API_KEY', None)
        self.use_api = bool(self.api_key)
        
        if self.use_api and SDK_AVAILABLE:
            trackingmore.api_key = self.api_key
    
    def detect_courier(self, tracking_number):
        """Detect which courier a tracking number belongs to."""
        if not self.use_api:
            return {"meta": {"code": 400, "message": "API key not configured"}}
        
        if not SDK_AVAILABLE:
            return {"meta": {"code": 500, "message": "TrackingMore SDK not installed"}}
        
        try:
            params = {"tracking_number": tracking_number}
            result = trackingmore.courier.detect(params)
            return {"meta": {"code": 200, "message": "OK"}, "data": result}
        except TrackingMoreException as e:
            logger.error(f"TrackingMore SDK error: {e}")
            return {"meta": {"code": 400, "message": str(e)}}
        except Exception as e:
            logger.error(f"TrackingMore error: {e}")
            return {"meta": {"code": 500, "message": str(e)}}
    
    def create_tracking(self, tracking_number, courier_code, title=None):
        """
        Create/import a tracking number to TrackingMore.
        Uses V4 API - create & get results in one call.
        """
        if not self.use_api:
            return {"meta": {"code": 400, "message": "API key not configured"}}
        
        if not SDK_AVAILABLE:
            return {"meta": {"code": 500, "message": "TrackingMore SDK not installed"}}
        
        try:
            params = {
                "tracking_number": tracking_number,
                "courier_code": courier_code
            }
            if title:
                params["title"] = title
            
            result = trackingmore.tracking.create_tracking(params)
            return {"meta": {"code": 201, "message": "Created"}, "data": result}
        except TrackingMoreException as e:
            logger.error(f"TrackingMore SDK error: {e}")
            return {"meta": {"code": 400, "message": str(e)}}
        except Exception as e:
            logger.error(f"TrackingMore error: {e}")
            return {"meta": {"code": 500, "message": str(e)}}
    
    def get_tracking(self, courier_code, tracking_number):
        """Get tracking results (V2 API)."""
        if not self.use_api:
            return {"meta": {"code": 400, "message": "API key not configured"}}
        
        if not SDK_AVAILABLE:
            return {"meta": {"code": 500, "message": "TrackingMore SDK not installed"}}
        
        try:
            result = trackingmore.tracking.get_tracking_results({
                "tracking_numbers": tracking_number,
                "courier_code": courier_code
            })
            return {"meta": {"code": 200, "message": "OK"}, "data": result}
        except TrackingMoreException as e:
            logger.error(f"TrackingMore SDK error: {e}")
            return {"meta": {"code": 400, "message": str(e)}}
        except Exception as e:
            logger.error(f"TrackingMore error: {e}")
            return {"meta": {"code": 500, "message": str(e)}}
    
    def get_realtime_tracking(self, courier_code, tracking_number):
        """Get realtime tracking results."""
        if not self.use_api:
            return {"meta": {"code": 400, "message": "API key not configured"}}
        
        if not SDK_AVAILABLE:
            return {"meta": {"code": 500, "message": "TrackingMore SDK not installed"}}
        
        try:
            params = {
                "tracking_number": tracking_number,
                "carrier_code": courier_code
            }
            result = trackingmore.tracking.get_realtime_tracking(params)
            return {"meta": {"code": 200, "message": "OK"}, "data": result}
        except TrackingMoreException as e:
            logger.error(f"TrackingMore SDK error: {e}")
            return {"meta": {"code": 400, "message": str(e)}}
        except Exception as e:
            logger.error(f"TrackingMore error: {e}")
            return {"meta": {"code": 500, "message": str(e)}}
    
    def update_tracking(self, tracking_id, params):
        """Update tracking by ID."""
        if not self.use_api:
            return {"meta": {"code": 400, "message": "API key not configured"}}
        
        if not SDK_AVAILABLE:
            return {"meta": {"code": 500, "message": "TrackingMore SDK not installed"}}
        
        try:
            result = trackingmore.tracking.update_tracking_by_id(tracking_id, params)
            return {"meta": {"code": 200, "message": "OK"}, "data": result}
        except TrackingMoreException as e:
            logger.error(f"TrackingMore SDK error: {e}")
            return {"meta": {"code": 400, "message": str(e)}}
        except Exception as e:
            logger.error(f"TrackingMore error: {e}")
            return {"meta": {"code": 500, "message": str(e)}}
    
    def delete_tracking(self, tracking_id):
        """Delete tracking by ID."""
        if not self.use_api:
            return {"meta": {"code": 400, "message": "API key not configured"}}
        
        if not SDK_AVAILABLE:
            return {"meta": {"code": 500, "message": "TrackingMore SDK not installed"}}
        
        try:
            result = trackingmore.tracking.delete_tracking_by_id(tracking_id)
            return {"meta": {"code": 200, "message": "OK"}, "data": result}
        except TrackingMoreException as e:
            logger.error(f"TrackingMore SDK error: {e}")
            return {"meta": {"code": 400, "message": str(e)}}
        except Exception as e:
            logger.error(f"TrackingMore error: {e}")
            return {"meta": {"code": 500, "message": str(e)}}
    
    def retrack(self, tracking_id):
        """Retrack expired tracking by ID."""
        if not self.use_api:
            return {"meta": {"code": 400, "message": "API key not configured"}}
        
        if not SDK_AVAILABLE:
            return {"meta": {"code": 500, "message": "TrackingMore SDK not installed"}}
        
        try:
            result = trackingmore.tracking.retrack_tracking_by_id(tracking_id)
            return {"meta": {"code": 200, "message": "OK"}, "data": result}
        except TrackingMoreException as e:
            logger.error(f"TrackingMore SDK error: {e}")
            return {"meta": {"code": 400, "message": str(e)}}
        except Exception as e:
            logger.error(f"TrackingMore error: {e}")
            return {"meta": {"code": 500, "message": str(e)}}
    
    def get_account_info(self):
        """Get account information."""
        if not self.use_api:
            return {"meta": {"code": 400, "message": "API key not configured"}}
        
        if not SDK_AVAILABLE:
            return {"meta": {"code": 500, "message": "TrackingMore SDK not installed"}}
        
        try:
            result = trackingmore.tracking.get_user_info()
            return {"meta": {"code": 200, "message": "OK"}, "data": result}
        except TrackingMoreException as e:
            logger.error(f"TrackingMore SDK error: {e}")
            return {"meta": {"code": 400, "message": str(e)}}
        except Exception as e:
            logger.error(f"TrackingMore error: {e}")
            return {"meta": {"code": 500, "message": str(e)}}


class LBCTracker:
    """LBC Tracker - uses TrackingMore SDK internally."""
    
    def __init__(self):
        self.tracking_more = TrackingMoreTracker()
        self.courier_code = "lbc-express"
    
    def register_lbc_tracking(self, tracking_number):
        """
        Register LBC tracking number with TrackingMore.
        Uses V4 API - creates tracking and gets results in real-time.
        """
        return self.tracking_more.create_tracking(
            tracking_number=tracking_number,
            courier_code=self.courier_code,
            title="CATC Student Document Request"
        )
    
    def get_status(self, tracking_number):
        """Get tracking status from TrackingMore."""
        result = self.tracking_more.get_tracking(self.courier_code, tracking_number)
        
        if result.get("meta", {}).get("code") == 200:
            data = result.get("data", {})
            
            # Handle V2 get_tracking_results response format
            # Response contains 'data' array with tracking items
            tracking_items = data.get("data", []) if isinstance(data, dict) else []
            
            if tracking_items:
                item = tracking_items[0]  # Get first tracking result
                
                # Extract status
                status = item.get("delivery_status", "Unknown")
                substatus = item.get("substatus", "")
                status_info = item.get("status_info", "")
                latest_event = item.get("latest_event", "")
                latest_checkpoint_time = item.get("latest_checkpoint_time", "")
                
                # Extract origin/destination info
                origin_info = item.get("origin_info", {})
                dest_info = item.get("destination_info", {})
                
                origin_checkpoints = origin_info.get("trackinfo", []) if origin_info else []
                dest_checkpoints = dest_info.get("trackinfo", []) if dest_info else []
                all_checkpoints = origin_checkpoints + dest_checkpoints
                
                # Build tracking details
                tracking_details = []
                for cp in all_checkpoints:
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