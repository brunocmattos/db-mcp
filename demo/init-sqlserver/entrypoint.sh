#!/bin/bash
set -e

/opt/mssql/bin/sqlservr &
PID=$!

echo "aguardando o SQL Server aceitar conexao..."
for i in {1..60}; do
  if /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -C -Q "SELECT 1" >/dev/null 2>&1; then
    echo "pronto apos ${i}s"
    for f in /init/*.sql; do
      echo "aplicando $f"
      # -f 65001: forca UTF-8 na leitura do arquivo (os seeds tem N'Sao Paulo' etc.
      # acentuado) -- sem isso o sqlcmd usa o codepage do container e mangla acento.
      /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -C -f 65001 -i "$f"
    done
    break
  fi
  sleep 1
done

wait $PID
