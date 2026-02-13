from rest_framework import status
from rest_framework.response import Response
from typing import Any, Dict, Optional, Union


class ResponseFormat:
    """Utility class for standardized API response formatting"""
    
    @staticmethod
    def success_response(
        message: str = "Operation completed successfully",
        data: Any = None,
        status_code: int = status.HTTP_200_OK,
        **kwargs
    ) -> Response:
        """
        Create a standardized success response
        
        Args:
            message: Success message
            data: Response data (can be dict, list, or any serializable object)
            status_code: HTTP status code
            **kwargs: Additional fields to include in response
        
        Returns:
            Response: Formatted success response
        """
        pass
    
    @staticmethod
    def error_response(
        message: str = "An error occurred",
        errors: Optional[Dict[str, Any]] = None,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        data: Any = None,
        **kwargs
    ) -> Response:
        """
        Create a standardized error response
        
        Args:
            message: Error message
            errors: Dictionary of field-specific errors
            status_code: HTTP status code
            data: Additional error data
            **kwargs: Additional fields to include in response
        
        Returns:
            Response: Formatted error response
        """
        response_data = {
            "success": False,
            "message": message,
        }
        
        if errors:
            response_data["errors"] = errors
        
        if data:
            response_data["data"] = data
        
        # Add any additional fields
        response_data.update(kwargs)
        
        return Response(response_data, status=status_code)
    
    @staticmethod
    def validation_error_response(
        message: str = "Validation failed",
        errors: Dict[str, Any] = None,
        **kwargs
    ) -> Response:
        """
        Create a standardized validation error response
        
        Args:
            message: Validation error message
            errors: Dictionary of field-specific validation errors
            **kwargs: Additional fields to include in response
        
        Returns:
            Response: Formatted validation error response
        """
        return ResponseFormat.error_response(
            message=message,
            errors=errors,
            status_code=status.HTTP_400_BAD_REQUEST,
            **kwargs
        )
    
    @staticmethod
    def not_found_response(
        message: str = "Resource not found",
        **kwargs
    ) -> Response:
        """
        Create a standardized not found response
        
        Args:
            message: Not found message
            **kwargs: Additional fields to include in response
        
        Returns:
            Response: Formatted not found response
        """
        return ResponseFormat.error_response(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            **kwargs
        )
    
    @staticmethod
    def unauthorized_response(
        message: str = "Authentication required",
        **kwargs
    ) -> Response:
        """
        Create a standardized unauthorized response
        
        Args:
            message: Unauthorized message
            **kwargs: Additional fields to include in response
        
        Returns:
            Response: Formatted unauthorized response
        """
        return ResponseFormat.error_response(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            **kwargs
        )
    
    @staticmethod
    def forbidden_response(
        message: str = "Access denied",
        **kwargs
    ) -> Response:
        """
        Create a standardized forbidden response
        
        Args:
            message: Forbidden message
            **kwargs: Additional fields to include in response
        
        Returns:
            Response: Formatted forbidden response
        """
        return ResponseFormat.error_response(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            **kwargs
        )
    
    @staticmethod
    def created_response(
        message: str = "Resource created successfully",
        data: Any = None,
        **kwargs
    ) -> Response:
        """
        Create a standardized created response
        
        Args:
            message: Creation success message
            data: Created resource data
            **kwargs: Additional fields to include in response
        
        Returns:
            Response: Formatted created response
        """
        return ResponseFormat.success_response(
            message=message,
            data=data,
            status_code=status.HTTP_201_CREATED,
            **kwargs
        )
    
    @staticmethod
    def no_content_response(
        message: str = "Operation completed successfully",
        **kwargs
    ) -> Response:
        """
        Create a standardized no content response
        
        Args:
            message: Success message
            **kwargs: Additional fields to include in response
        
        Returns:
            Response: Formatted no content response
        """
        return ResponseFormat.success_response(
            message=message,
            data=None,
            status_code=status.HTTP_204_NO_CONTENT,
            **kwargs
        )


# Convenience functions for common use cases
def success_response(message: str = "Operation completed successfully", data: Any = None, **kwargs) -> Response:
    """Convenience function for success response"""
    return ResponseFormat.success_response(message, data, **kwargs)

def error_response(message: str = "An error occurred", errors: Dict[str, Any] = None, **kwargs) -> Response:
    """Convenience function for error response"""
    return ResponseFormat.error_response(message, errors, **kwargs)

def validation_error_response(message: str = "Validation failed", errors: Dict[str, Any] = None, **kwargs) -> Response:
    """Convenience function for validation error response"""
    return ResponseFormat.validation_error_response(message, errors, **kwargs)

def not_found_response(message: str = "Resource not found", **kwargs) -> Response:
    """Convenience function for not found response"""
    return ResponseFormat.not_found_response(message, **kwargs)

def unauthorized_response(message: str = "Authentication required", **kwargs) -> Response:
    """Convenience function for unauthorized response"""
    return ResponseFormat.unauthorized_response(message, **kwargs)

def forbidden_response(message: str = "Access denied", **kwargs) -> Response:
    """Convenience function for forbidden response"""
    return ResponseFormat.forbidden_response(message, **kwargs)

def created_response(message: str = "Resource created successfully", data: Any = None, **kwargs) -> Response:
    """Convenience function for created response"""
    return ResponseFormat.created_response(message, data, **kwargs)

def no_content_response(message: str = "Operation completed successfully", **kwargs) -> Response:
    """Convenience function for no content response"""
    return ResponseFormat.no_content_response(message, **kwargs)
