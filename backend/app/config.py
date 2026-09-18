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
    def resolved_model_dir(self) -> str:
        """把 ``model_dir`` 规范化为"本地绝对路径"或"ModelScope 仓库 id"。

        ``model_dir`` 有两种合法写法，必须区分开，否则会把本地路径当成仓库 id
        去下载（ModelScope 会抛出难以理解的错误）：

        * 仓库 id：``iic/CosyVoice2-0.5B``  → 原样返回，交给 snapshot_download；
        * 本地路径：``../CosyVoice/pretrained_models/xxx``、``~/models/xxx``、
          ``/abs/path``、``pretrained_models/xxx`` → 统一解析为绝对路径，
          这样不会再受进程工作目录（加载模型时上游会 chdir）影响。

        相对路径会依次尝试相对 ``backend/`` 与相对 CosyVoice 仓库解析
        （上游示例习惯用后者）。
        """
        raw = self.model_dir.strip()
        if not raw:
            return raw

        path = Path(raw).expanduser()
        if path.is_absolute():
            return str(path)

        # 相对写法但真实存在：按实际所在位置解析
        for base in (BACKEND_DIR, self.resolved_cosyvoice_repo):
            candidate = (base / path).resolve()
            if candidate.exists():
                return str(candidate)

        # 不存在的相对写法：带路径特征的一律按 backend/ 解析成绝对路径，
        # 由上层抛出"目录不存在"的明确错误；否则视为 ModelScope 仓库 id。
        parts = [segment for segment in raw.split("/") if segment]
        path_like = raw.startswith((".", "~")) or ".." in raw or len(parts) > 2
        if path_like:
            return str((BACKEND_DIR / path).resolve())
        return raw

    @property
    def model_source(self) -> Literal["local", "remote"]:
        """判断 ``model_dir`` 指向本地目录还是 ModelScope 仓库 id。"""
        return "local" if Path(self.resolved_model_dir).is_absolute() else "remote"

    def ensure_directories(self) -> None:
        for directory in (self.resolved_data_dir, self.voices_dir, self.outputs_dir, self.tmp_dir):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
