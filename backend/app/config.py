"""应用配置。

所有配置项均支持通过环境变量覆盖，前缀为 ``CV_``（例如 ``CV_MODEL_DIR``），
也可以写在 ``backend/.env`` 中。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """后端配置集合。"""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        env_prefix="CV_",
        extra="ignore",
        case_sensitive=False,
        # model_dir / model_source 等字段名与 pydantic 的 model_ 保护前缀冲突，这里放开
        protected_namespaces=("settings_",),
    )

    # ------------------------------------------------------------------ 服务
    app_name: str = "CosyVoice Web API"
    app_version: str = "1.0.0"
    api_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )

    # ------------------------------------------------------- CosyVoice 运行时
    cosyvoice_repo: Path = PROJECT_ROOT / "CosyVoice"
    model_dir: str = "iic/CosyVoice2-0.5B"
    load_jit: bool = False
    load_trt: bool = False
    load_vllm: bool = False
    fp16: bool = False
    mock: bool = False
    preload_model: bool = False

    # --------------------------------------------------------------- 数据目录
    data_dir: Path = PROJECT_ROOT / "data"
    max_upload_mb: int = 30
    max_prompt_seconds: float = 30.0
    min_prompt_seconds: float = 0.5
    default_speed: float = 1.0
    max_speed: float = 2.0
    min_speed: float = 0.5
    # 保留的生成结果数量，超出后自动清理最旧文件
    max_history_files: int = 200

    # ----------------------------------------------------------------- 校验
    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        return value.upper()

    @field_validator(
        "cosyvoice_repo",
        "data_dir",
        mode="after",
    )
    @classmethod
    def _expand_path(cls, value: Path) -> Path:
        return value.expanduser()

    # --------------------------------------------------------------- 派生属性
    @property
    def resolved_cosyvoice_repo(self) -> Path:
        """CosyVoice 仓库的绝对路径（相对路径按 backend/ 解析）。"""
        repo = self.cosyvoice_repo
        if not repo.is_absolute():
            repo = (BACKEND_DIR / repo).resolve()
        return repo

    @property
    def voices_dir(self) -> Path:
        return self.resolved_data_dir / "voices"

    @property
    def outputs_dir(self) -> Path:
        return self.resolved_data_dir / "outputs"

    @property
    def tmp_dir(self) -> Path:
        return self.resolved_data_dir / "tmp"

    @property
    def resolved_data_dir(self) -> Path:
        data = self.data_dir
        if not data.is_absolute():
            data = (BACKEND_DIR / data).resolve()
        return data

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def model_source(self) -> Literal["local", "remote"]:
        """判断 ``model_dir`` 指向本地目录还是 ModelScope 仓库 id。"""
        path = Path(self.model_dir).expanduser()
        return "local" if path.exists() else "remote"

    def ensure_directories(self) -> None:
        for directory in (self.resolved_data_dir, self.voices_dir, self.outputs_dir, self.tmp_dir):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
