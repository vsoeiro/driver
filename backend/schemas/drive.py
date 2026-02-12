"""Drive schemas.

Pydantic models for OneDrive file and folder API responses.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class DriveItemBase(BaseModel):
    """Base model for OneDrive items.

    Attributes
    ----------
    id : str
        Item ID from OneDrive.
    name : str
        Item name.
    size : int
        Item size in bytes, 0 for folders.
    created_at : datetime
        Item creation timestamp.
    modified_at : datetime
        Last modification timestamp.
    web_url : str
        Web URL to access the item.
    """

    id: str
    name: str
    size: int = 0
    created_at: datetime | None = None
    modified_at: datetime | None = None
    web_url: str | None = None


class DriveFolder(DriveItemBase):
    """Model for OneDrive folder.

    Attributes
    ----------
    child_count : int
        Number of children in the folder.
    """

    item_type: str = Field(default="folder", description="Item type")
    child_count: int = 0


class DriveFile(DriveItemBase):
    """Model for OneDrive file.

    Attributes
    ----------
    mime_type : str
        File MIME type.
    download_url : str
        Direct download URL (temporary).
    """

    item_type: str = Field(default="file", description="Item type")
    mime_type: str | None = None
    download_url: str | None = None


class DriveItem(BaseModel):
    """Generic OneDrive item that can be a file or folder.

    Attributes
    ----------
    id : str
        Item ID.
    name : str
        Item name.
    item_type : str
        Either 'file' or 'folder'.
    size : int
        Size in bytes.
    mime_type : str
        MIME type for files.
    child_count : int
        Child count for folders.
    created_at : datetime
        Creation timestamp.
    modified_at : datetime
        Last modification timestamp.
    web_url : str
        Web URL.
    download_url : str
        Download URL for files.
    """

    id: str
    name: str
    item_type: str
    size: int = 0
    mime_type: str | None = None
    child_count: int | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None
    web_url: str | None = None
    download_url: str | None = None


class DriveListResponse(BaseModel):
    """Response for listing drive items.

    Attributes
    ----------
    items : list[DriveItem]
        List of drive items.
    folder_path : str
        Current folder path.
    next_link : str
        Pagination link for next page.
    """

    items: list[DriveItem] = Field(default_factory=list)
    folder_path: str = "/"
    next_link: str | None = None


class DriveQuota(BaseModel):
    """OneDrive storage quota information.

    Attributes
    ----------
    total : int
        Total storage in bytes.
    used : int
        Used storage in bytes.
    remaining : int
        Remaining storage in bytes.
    state : str
        Quota state (normal, nearing, critical, exceeded).
    """

    total: int
    used: int
    remaining: int
    state: str = "normal"


class UploadSessionRequest(BaseModel):
    """Request to create an upload session for large files.

    Attributes
    ----------
    filename : str
        Name of the file to upload.
    file_size : int
        Total size of the file in bytes.
    folder_id : str
        Target folder ID. Use 'root' for root folder.
    conflict_behavior : str
        What to do if file exists: 'rename', 'replace', or 'fail'.
    """

    filename: str
    file_size: int
    folder_id: str = "root"
    conflict_behavior: str = "rename"


class UploadSession(BaseModel):
    """Upload session for resumable uploads.

    Attributes
    ----------
    upload_url : str
        URL to upload chunks to.
    expiration : datetime
        When the session expires.
    next_expected_ranges : list[str]
        Byte ranges the server expects next.
    """

    upload_url: str
    expiration: datetime
    next_expected_ranges: list[str] = Field(default_factory=list)


class BreadcrumbItem(BaseModel):
    """Single item in breadcrumb path.

    Attributes
    ----------
    id : str
        Item ID.
    name : str
        Item name.
    """

    id: str
    name: str


class PathResponse(BaseModel):
    """Full path/breadcrumb for a drive item.

    Attributes
    ----------
    breadcrumb : list[BreadcrumbItem]
        List of items from root to current item.
    """

    breadcrumb: list[BreadcrumbItem] = Field(default_factory=list)


class SearchRequest(BaseModel):
    """Search request parameters.

    Attributes
    ----------
    query : str
        Search query string.
    """

class CreateFolderRequest(BaseModel):
    """Request to create a new folder.

    Attributes
    ----------
    name : str
        Folder name.
    parent_folder_id : str
        Parent folder ID. Defaults to "root".
    conflict_behavior : str
        Conflict behavior: 'rename', 'replace', 'fail'.
    """

    name: str = Field(..., min_length=1, max_length=255)
    parent_folder_id: str = "root"
    conflict_behavior: str = "rename"


class UpdateItemRequest(BaseModel):
    """Request to update (rename/move) an item.

    Attributes
    ----------
    name : str | None
        New name for the item.
    parent_folder_id : str | None
        New parent folder ID (to move the item).
    """

    name: str | None = Field(None, min_length=1, max_length=255)
    parent_folder_id: str | None = None


class CopyItemRequest(BaseModel):
    """Request to copy an item.

    Attributes
    ----------
    name : str | None
        New name for the copy. If None, uses original name.
    parent_folder_id : str
        Target folder ID. Defaults to "root".
    """

    name: str | None = Field(None, min_length=1, max_length=255)
    parent_folder_id: str = "root"


class BulkDownloadRequest(BaseModel):
    """Request to download multiple files as a ZIP archive.

    Attributes
    ----------
    item_ids : list[str]
        List of file item IDs to include in the archive.
    archive_name : str | None
        Optional output archive name.
    """

    item_ids: list[str] = Field(..., min_length=1, max_length=100)
    archive_name: str | None = Field(default=None, min_length=1, max_length=128)


