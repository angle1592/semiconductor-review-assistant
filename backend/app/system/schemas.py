from pydantic import BaseModel


class SystemInfo(BaseModel):
    application: str
    version: str
    packaged: bool
    setup_complete: bool
    data_directory: str
    log_directory: str
