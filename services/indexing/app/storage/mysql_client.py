"""MySQL client for parent nodes and metadata storage."""

import json
from typing import List, Optional, Dict, Any
from datetime import datetime

from sqlalchemy import create_engine, text, Column, String, Text, JSON, TIMESTAMP, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from app.utils.logger import logger

Base = declarative_base()


class ParentNode(Base):
    """Parent node table model."""

    __tablename__ = "parent_nodes"

    id = Column(String(255), primary_key=True)
    collection_name = Column(String(255), nullable=False, index=True)
    file_name = Column(String(255), nullable=False, index=True)
    text = Column(Text, nullable=False)  # Context text + base64 images
    metadata = Column(JSON)  # {user_role, page, images: [...]}
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)


class Collection(Base):
    """Collection metadata table."""

    __tablename__ = "collections"

    name = Column(String(255), primary_key=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    point_count = Column(Integer, default=0)


class Document(Base):
    """Document metadata table."""

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    collection_name = Column(String(255), nullable=False, index=True)
    file_name = Column(String(255), nullable=False)
    indexed_at = Column(TIMESTAMP, default=datetime.utcnow)


class MySQLClient:
    """MySQL client for parent nodes and metadata management."""

    def __init__(self, connection_url: str):
        """Initialize MySQL client.

        Args:
            connection_url: SQLAlchemy connection URL
                (e.g., "mysql+pymysql://user:pass@host:port/db")
        """
        self.engine = create_engine(connection_url, pool_pre_ping=True)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self._create_tables()

    def _create_tables(self):
        """Create tables if they don't exist."""
        Base.metadata.create_all(self.engine)
        logger.info("MySQL tables initialized")

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    # ──────────────────── Parent Nodes ────────────────────

    def insert_parent_nodes(self, nodes: List[Dict[str, Any]]):
        """Insert parent nodes into MySQL.

        Args:
            nodes: List of parent node dicts with keys:
                - id: Node ID
                - collection_name: Collection name
                - file_name: Source file name
                - text: Context text + base64 images
                - metadata: JSON metadata
        """
        session = self.get_session()
        try:
            for node_data in nodes:
                parent_node = ParentNode(
                    id=node_data["id"],
                    collection_name=node_data["collection_name"],
                    file_name=node_data["file_name"],
                    text=node_data["text"],
                    metadata=node_data.get("metadata", {}),
                )
                session.merge(parent_node)  # Insert or update
            session.commit()
            logger.info(f"Inserted {len(nodes)} parent nodes into MySQL")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to insert parent nodes: {e}")
            raise
        finally:
            session.close()

    def get_parent_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get parent node by ID.

        Args:
            node_id: Parent node ID

        Returns:
            Parent node dict or None if not found
        """
        session = self.get_session()
        try:
            node = session.query(ParentNode).filter(ParentNode.id == node_id).first()
            if node:
                return {
                    "id": node.id,
                    "collection_name": node.collection_name,
                    "file_name": node.file_name,
                    "text": node.text,
                    "metadata": node.metadata,
                }
            return None
        finally:
            session.close()

    def get_parent_nodes_by_ids(self, node_ids: List[str]) -> List[Dict[str, Any]]:
        """Get multiple parent nodes by IDs.

        Args:
            node_ids: List of parent node IDs

        Returns:
            List of parent node dicts
        """
        session = self.get_session()
        try:
            nodes = session.query(ParentNode).filter(ParentNode.id.in_(node_ids)).all()
            return [
                {
                    "id": node.id,
                    "collection_name": node.collection_name,
                    "file_name": node.file_name,
                    "text": node.text,
                    "metadata": node.metadata,
                }
                for node in nodes
            ]
        finally:
            session.close()

    def delete_parent_nodes_by_collection_and_file(
        self, collection_name: str, file_name: str
    ):
        """Delete parent nodes by collection and file name.

        Args:
            collection_name: Collection name
            file_name: File name
        """
        session = self.get_session()
        try:
            session.query(ParentNode).filter(
                ParentNode.collection_name == collection_name,
                ParentNode.file_name == file_name,
            ).delete()
            session.commit()
            logger.info(
                f"Deleted parent nodes for {file_name} in {collection_name}"
            )
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to delete parent nodes: {e}")
            raise
        finally:
            session.close()

    # ──────────────────── Collections ────────────────────

    def create_collection(self, collection_name: str):
        """Create collection metadata entry.

        Args:
            collection_name: Collection name
        """
        session = self.get_session()
        try:
            collection = Collection(name=collection_name)
            session.merge(collection)
            session.commit()
            logger.info(f"Created collection metadata: {collection_name}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create collection metadata: {e}")
            raise
        finally:
            session.close()

    def list_collections(self) -> List[Dict[str, Any]]:
        """List all collections.

        Returns:
            List of collection dicts with name, created_at, point_count
        """
        session = self.get_session()
        try:
            collections = session.query(Collection).all()
            return [
                {
                    "name": c.name,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "point_count": c.point_count,
                }
                for c in collections
            ]
        finally:
            session.close()

    def update_collection_point_count(self, collection_name: str, point_count: int):
        """Update collection point count.

        Args:
            collection_name: Collection name
            point_count: New point count
        """
        session = self.get_session()
        try:
            collection = (
                session.query(Collection)
                .filter(Collection.name == collection_name)
                .first()
            )
            if collection:
                collection.point_count = point_count
                session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update collection point count: {e}")
            raise
        finally:
            session.close()

    def delete_collection(self, collection_name: str):
        """Delete collection metadata.

        Args:
            collection_name: Collection name
        """
        session = self.get_session()
        try:
            session.query(Collection).filter(
                Collection.name == collection_name
            ).delete()
            session.commit()
            logger.info(f"Deleted collection metadata: {collection_name}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to delete collection metadata: {e}")
            raise
        finally:
            session.close()

    # ──────────────────── Documents ────────────────────

    def add_document(self, collection_name: str, file_name: str):
        """Add document metadata entry.

        Args:
            collection_name: Collection name
            file_name: File name
        """
        session = self.get_session()
        try:
            document = Document(
                collection_name=collection_name,
                file_name=file_name,
            )
            session.add(document)
            session.commit()
            logger.info(f"Added document metadata: {file_name} in {collection_name}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to add document metadata: {e}")
            raise
        finally:
            session.close()

    def list_documents(self, collection_name: str) -> List[str]:
        """List all documents in a collection.

        Args:
            collection_name: Collection name

        Returns:
            List of file names
        """
        session = self.get_session()
        try:
            documents = (
                session.query(Document.file_name)
                .filter(Document.collection_name == collection_name)
                .distinct()
                .all()
            )
            return [doc[0] for doc in documents]
        finally:
            session.close()

    def delete_document(self, collection_name: str, file_name: str):
        """Delete document metadata.

        Args:
            collection_name: Collection name
            file_name: File name
        """
        session = self.get_session()
        try:
            session.query(Document).filter(
                Document.collection_name == collection_name,
                Document.file_name == file_name,
            ).delete()
            session.commit()
            logger.info(f"Deleted document metadata: {file_name} in {collection_name}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to delete document metadata: {e}")
            raise
        finally:
            session.close()
