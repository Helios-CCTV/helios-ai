import os


class AnalyzeSettings:
    def __init__(self) -> None:
        # Swift public access
        self.SWIFT_PUBLIC_BASE_URL: str = os.getenv(
            "SWIFT_PUBLIC_BASE_URL",
            "http://example.com/v1/AUTH_xxx/cctv-preprocess/",
        ).rstrip("/") + "/"
        self.SWIFT_CONTAINER: str = os.getenv("SWIFT_CONTAINER", "cctv-preprocess")
        self.SWIFT_UPLOAD_PREFIX: str = os.getenv("SWIFT_UPLOAD_PREFIX", "")

        # Model
        self.MODEL_PATH: str = os.getenv("ANALYZE_MODEL_PATH", "models/09-08-best-final-model.pt")
        self.YOLO_CONF_THRESH: float = float(os.getenv("YOLO_CONF_THRESH", "0.25"))
        self.YOLO_IOU_THRESH: float = float(os.getenv("YOLO_IOU_THRESH", "0.5"))

        # Drawing/output
        self.OUTPUT_MAX_WIDTH: int = int(os.getenv("OUTPUT_MAX_WIDTH", "1920"))
        self.JPEG_QUALITY: int = int(os.getenv("JPEG_QUALITY", "85"))

        # DB
        self.MYSQL_HOST: str = os.getenv("MYSQL_HOST", "127.0.0.1")
        self.MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
        self.MYSQL_DB: str = os.getenv("MYSQL_DB", "helios")
        self.MYSQL_USER: str = os.getenv("MYSQL_USER", "helios")
        self.MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "password")
        self.MYSQL_CHARSET: str = os.getenv("MYSQL_CHARSET", "utf8mb4")

        # Severity thresholds (area ratio of image)
        self.SEVERITY_AREA_LOW: float = float(os.getenv("SEVERITY_AREA_LOW", "0.02"))
        self.SEVERITY_AREA_MED: float = float(os.getenv("SEVERITY_AREA_MED", "0.10"))


analyze_settings = AnalyzeSettings()
