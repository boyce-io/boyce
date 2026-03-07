"""Safety Kernel Exception Hierarchy.

This module defines the exception classes used throughout the Safety Kernel
to signal governance violations, policy errors, and integrity failures.
"""


class DataSharkKernelError(Exception):
    """Base exception for all Safety Kernel errors.
    
    All kernel-related exceptions inherit from this class to provide
    a unified exception hierarchy for error handling and logging.
    """
    pass


class GovernanceViolationError(DataSharkKernelError):
    """Raised when access control policies are violated.
    
    This exception is raised when an untrusted component attempts to
    access resources or perform operations that are not permitted
    by the current user context or security policies.
    """
    pass


class PolicyNotFoundException(DataSharkKernelError):
    """Raised when required policy configuration is missing.
    
    This exception is raised when the kernel attempts to load or
    evaluate a policy that does not exist or is not properly configured.
    """
    pass


class SnapshotIntegrityError(DataSharkKernelError):
    """Raised when snapshot hash verification fails.
    
    This exception is raised when a snapshot's integrity cannot be
    verified, typically due to hash mismatch or corrupted snapshot data.
    """
    pass


class SnapshotNotFoundError(SnapshotIntegrityError):
    """Raised when a snapshot is not found in CAS."""
    pass


class ContextValidationError(DataSharkKernelError):
    """Raised when user context validation fails.
    
    This exception is raised when a UserContext object does not meet
    the required validation criteria (missing fields, invalid types,
    or malformed data).
    """
    pass

