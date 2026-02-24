"""Ingestion Service API 路由。"""

import shutil
import traceback
from pathlib import Path
from typing import List

from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import JSONResponse

from rag_shared.config.experiment import ExperimentConfig
from rag_shared.schemas.ingestion import (
    IngestRequest,
    IngestResponse,
    BatchIngestRequest,
    BatchIngestResponse,
    BatchIngestResult,
    CollectionInfo,
    FileInfo,
    DocumentDeleteResponse,
)

from app.config import service_settings
from app.services.ingestion import IngestionService
from app.storage.vectordb import VectorStoreManager
from app.storage.metadata import DatabaseManager

router = APIRouter()


def _build_config(config_dict: dict) -> ExperimentConfig:
    """从请求字典构建 ExperimentConfig，注入服务级默认值。"""
    config_dict.setdefault("qdrant_url", service_settings.qdrant_url)
    config_dict.setdefault("dashscope_api_key", service_settings.dashscope_api_key)
    return ExperimentConfig.from_dict(config_dict)


def _get_db(collection_name: str) -> DatabaseManager:
    return DatabaseManager(
        db_path=service_settings.metadata_db_path,
        collection_name=collection_name,
    )


@router.post("/documents/upload", response_model=IngestResponse)
async def upload_and_ingest(
    files: List[UploadFile] = File(...),
    config: str = Form("{}"),
):
    """上传文件并自动向量化入库。"""
    import json
    try:
        config_dict = json.loads(config)
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"detail": "Invalid config JSON"})

    upload_dir = Path(service_settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []
    for f in files:
        target = upload_dir / f.filename
        with open(target, "wb") as out:
            shutil.copyfileobj(f.file, out)
        saved_paths.append(str(target))

    cfg = _build_config(config_dict)
    db = _get_db(cfg.collection_name)

    # 过滤已入库文件
    indexed = set(db.get_all_files())
    new_paths = [p for p in saved_paths if Path(p).name not in indexed]

    if not new_paths:
        return IngestResponse(
            status="skipped",
            message=f"All {len(saved_paths)} files already indexed",
            collection_name=cfg.collection_name,
        )

    try:
        service = IngestionService(cfg)
        result = await service.process_files(new_paths)
        for p in new_paths:
            db.add_file(Path(p).name)

        # 处理层级切分结果
        if isinstance(result, dict):
            return IngestResponse(
                status="success",
                message=f"Hierarchical ingestion: {result['child_count']} child nodes vectorized",
                collection_name=cfg.collection_name,
                parent_count=result["parent_count"],
                child_count=result["child_count"],
                vectorized_count=result["vectorized_count"],
                is_hierarchical=True,
            )
        else:
            # 扁平化切分（向后兼容）
            return IngestResponse(
                status="success",
                message=f"Flat ingestion: {len(new_paths)} files processed",
                collection_name=cfg.collection_name,
                chunks_count=0,
                is_hierarchical=False,
            )
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"detail": str(e)})


@router.post("/documents/ingest", response_model=IngestResponse)
async def ingest_files(request: IngestRequest):
    """对已有文件路径执行向量化入库。"""
    cfg = _build_config(request.config)
    try:
        service = IngestionService(cfg)
        result = await service.process_files(request.file_paths)

        # 处理层级切分结果
        if isinstance(result, dict):
            return IngestResponse(
                status="success",
                message=f"Hierarchical ingestion: {result['child_count']} child nodes vectorized",
                collection_name=cfg.collection_name,
                parent_count=result["parent_count"],
                child_count=result["child_count"],
                vectorized_count=result["vectorized_count"],
                is_hierarchical=True,
            )
        else:
            # 扁平化切分（向后兼容）
            return IngestResponse(
                status="success",
                message=f"Flat ingestion: {len(request.file_paths)} files processed",
                collection_name=cfg.collection_name,
                chunks_count=0,
                is_hierarchical=False,
            )
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"detail": str(e)})


@router.post("/batch/ingest", response_model=BatchIngestResponse)
async def batch_ingest(request: BatchIngestRequest):
    """批量智能入库：按 fingerprint 去重，跳过已有 collection。"""
    results = []
    groups: dict[str, ExperimentConfig] = {}

    for cfg_dict in request.configs:
        cfg = _build_config(cfg_dict)
        fp = cfg.ingestion_fingerprint
        if fp not in groups:
            groups[fp] = cfg

    for fp, cfg in groups.items():
        store = VectorStoreManager(cfg)
        if store.collection_exists() and store.collection_point_count() > 0:
            results.append(BatchIngestResult(
                collection_name=cfg.collection_name,
                status="skipped",
                point_count=store.collection_point_count(),
                message="Collection already populated",
            ))
            continue

        try:
            service = IngestionService(cfg)
            await service.process_directory(request.input_dir)
            results.append(BatchIngestResult(
                collection_name=cfg.collection_name,
                status="success",
                point_count=store.collection_point_count(),
            ))
        except Exception as e:
            traceback.print_exc()
            results.append(BatchIngestResult(
                collection_name=cfg.collection_name,
                status="error",
                message=str(e),
            ))

    return BatchIngestResponse(results=results)


@router.get("/collections", response_model=List[CollectionInfo])
async def list_collections():
    """列出所有 Qdrant collections。"""
    from qdrant_client import QdrantClient
    client = QdrantClient(url=service_settings.qdrant_url)
    try:
        collections = client.get_collections().collections
        result = []
        for c in collections:
            try:
                info = client.get_collection(c.name)
                result.append(CollectionInfo(
                    name=c.name,
                    point_count=info.points_count or 0,
                ))
            except Exception:
                result.append(CollectionInfo(name=c.name, point_count=0, status="error"))
        return result
    finally:
        client.close()


@router.get("/collections/{name}/files", response_model=List[FileInfo])
async def list_collection_files(name: str):
    """列出指定 collection 中已入库的文件。"""
    db = _get_db(name)
    files = db.get_all_files()
    return [FileInfo(filename=f) for f in files]


@router.delete("/documents/{collection_name}/{filename}", response_model=DocumentDeleteResponse)
async def delete_document(collection_name: str, filename: str):
    """从指定 collection 删除文档。"""
    cfg = _build_config({
        "collection_name_override": collection_name,
    })
    store = VectorStoreManager(cfg)
    db = _get_db(collection_name)

    success = store.delete_file(filename)
    db.remove_file(filename)

    return DocumentDeleteResponse(
        status="success" if success else "partial",
        message=f"Deleted {filename} from {collection_name}",
    )
