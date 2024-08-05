import logging
import struct
from typing import Dict, Generator, Any, Tuple, Optional
from contextlib import contextmanager

import numpy as np
import mysql.connector as mysql
from ..api import VectorDB, IndexType, MetricType
from .config import OceanBaseIndexConfig, OceanBaseConfigDict

log = logging.getLogger(__name__)

OCEANBASE_DEFAULT_LOAD_BATCH_SIZE = 1000

class OceanBase(VectorDB):
    def __init__(
        self,
        dim: int,
        db_config: OceanBaseConfigDict,
        db_case_config: OceanBaseIndexConfig,
        collection_name: str = "items",
        drop_old: bool = False,
        **kwargs,
    ):
        self.name = "OceanBase"
        self.db_config = db_config
        self.db_case_config = db_case_config
        self.table_name = collection_name
        self.dim = dim
        self.load_batch_size = OCEANBASE_DEFAULT_LOAD_BATCH_SIZE
        
        self._index_name = "vidx"
        self._primary_field = "id"
        self._vector_field = "embedding"
        self._query = f"SELECT /*+ opt_param('rowsets_max_rows', 256) */ id FROM {self.table_name} ORDER BY {self.db_case_config.parse_metric_func_str()}(embedding, 0x%s) APPROXIMATE LIMIT %s"

        log.info(f"{self.name} config values: {self.db_config}\n{self.db_case_config}")

        if self.db_config["unix_socket"] != "":
            self._conn = mysql.connect(unix_socket=self.db_config["unix_socket"],
                                       user=self.db_config["user"],
                                       port=self.db_config["port"],
                                       password=self.db_config["password"],
                                       database=self.db_config["database"])
        else:
            self._conn = mysql.connect(host=self.db_config["host"],
                                       user=self.db_config["user"],
                                       port=self.db_config["port"],
                                       password=self.db_config["password"],
                                       database=self.db_config["database"])
        self._cursor = self._conn.cursor()

        if drop_old:
            self._drop_table()
            self._create_table()

        self._cursor.close()
        self._cursor = None
        self._conn.close()
        self._conn = None

    @contextmanager
    def init(self) -> Generator[None, None, None]:
        try:
            if self.db_config["unix_socket"] != "":
                self._conn = mysql.connect(unix_socket=self.db_config["unix_socket"],
                                           user=self.db_config["user"],
                                           port=self.db_config["port"],
                                           password=self.db_config["password"],
                                           database=self.db_config["database"])
            else:
                self._conn = mysql.connect(host=self.db_config["host"],
                                           user=self.db_config["user"],
                                           port=self.db_config["port"],
                                           password=self.db_config["password"],
                                           database=self.db_config["database"])
            self._cursor = self._conn.cursor()
            self._cursor.execute("SET autocommit=1")
            if self.db_case_config.index == IndexType.HNSW:
                self._cursor.execute(f"SET ob_hnsw_ef_search={(self.db_case_config.search_param())['params']['ef_search']}")
            else:
                raise ValueError("Index type is not supported")
            
            yield
        finally:
            self._cursor.close()
            self._cursor = None
            self._conn.close()
            self._conn = None

    def _drop_table(self):
        if (self._conn is None) or (self._cursor is None):
            raise ValueError("connection is invalid")
        
        log.info(f"{self.name} client drop table: {self.table_name}")
        self._cursor.execute(
            f"DROP TABLE IF EXISTS {self.table_name}"
        )
    
    def _create_table(self):
        if (self._conn is None) or (self._cursor is None):
            raise ValueError("connection is invalid")
        
        log.info(f"{self.name} client create table: {self.table_name}")
        idx_param = self.db_case_config.index_param()
        idx_args_str = ','.join([f"{k}={v}" for k, v in idx_param["params"].items()])
        self._cursor.execute(
            f"CREATE TABLE {self.table_name} (id INT, embedding vector({self.dim}), primary key(id), vector index idx1(embedding) with(distance={idx_param['metric_type']}, type={idx_param['index_type']}, lib={idx_param['lib']}, {idx_args_str}))"
        )

    def ready_to_load(self):
        pass

    def optimize(self):
        pass

    def need_normalize_cosine(self) -> bool:
        return self.db_case_config.metric_type == MetricType.IP or self.db_case_config.metric_type == MetricType.COSINE

    def insert_embeddings(
        self,
        embeddings: list[list[float]],
        metadata: list[int],
        **kwargs: Any,
    ) -> Tuple[int, Optional[Exception]]:
        if (self._conn is None) or (self._cursor is None):
            raise ValueError("connection is invalid")
        
        insert_count = 0
        try:
            for batch_start_offset in range(0, len(embeddings), self.load_batch_size):
                batch_end_offset = min(batch_start_offset + self.load_batch_size, len(embeddings))
                values_str = ",".join([f"({id}, 0x{struct.pack('f' * len(vec), *vec).hex()})" for id, vec in zip(metadata[batch_start_offset : batch_end_offset], embeddings[batch_start_offset : batch_end_offset])])
                self._cursor.execute(f"insert into {self.table_name} values {values_str}")
                insert_count += (batch_end_offset - batch_start_offset)
        except mysql.Error as e:
            log.info(f"Failed to insert data: {e}")
            return (insert_count, e)
        return (insert_count, None)

    def search_embedding(
        self,
        query: list[float],
        k: int = 100,
        filters: dict | None = None,
        timeout: int | None = None,
    ) -> list[int]:
        if (self._conn is None) or (self._cursor is None):
            raise ValueError("connection is invalid")
        
        if filters is not None:
            raise ValueError("filters is not supported now")

        self._cursor.execute(self._query % (struct.pack('f' * len(query), *query).hex(), k))
        return [id for id, in self._cursor.fetchall()]