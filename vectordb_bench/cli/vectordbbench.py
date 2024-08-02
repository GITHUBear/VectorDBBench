from ..backend.clients.pgvector.cli import PgVectorHNSW
from ..backend.clients.redis.cli import Redis
from ..backend.clients.test.cli import Test
from ..backend.clients.weaviate_cloud.cli import Weaviate
from ..backend.clients.zilliz_cloud.cli import ZillizAutoIndex
from ..backend.clients.milvus.cli import MilvusAutoIndex
from ..backend.clients.aws_opensearch.cli import AWSOpenSearch
from ..backend.clients.oceanbase.cli import OceanBaseHNSW


from .cli import cli

cli.add_command(PgVectorHNSW)
cli.add_command(Redis)
cli.add_command(Weaviate)
cli.add_command(Test)
cli.add_command(ZillizAutoIndex)
cli.add_command(MilvusAutoIndex)
cli.add_command(AWSOpenSearch)
cli.add_command(OceanBaseHNSW)

if __name__ == "__main__":
    cli()
