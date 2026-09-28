import os
import time
import glob
import pandas as pd

def find_file(extension):
    # Procura arquivos na pasta dados/silver/ ou no diretório atual/pai
    search_paths = [
        f"../dados/silver/*.{extension}",
        f"dados/silver/*.{extension}",
        f"../dados/silver/*{extension}*",
        f"dados/silver/*{extension}*"
    ]
    for path in search_paths:
        matches = glob.glob(path)
        if matches:
            return matches[0]
    return None

def measure_format(ext, read_func):
    file_path = find_file(ext)
    if not file_path or not os.path.exists(file_path):
        return "Arquivo não encontrado", "N/A"
    
    # Tamanho em KB (se for diretório, soma o tamanho de todos os arquivos internos)
    if os.path.isdir(file_path):
        size_bytes = sum(os.path.getsize(os.path.join(file_path, f)) for f in os.listdir(file_path) if os.path.isfile(os.path.join(file_path, f)))
    else:
        size_bytes = os.path.getsize(file_path)
    
    size_kb = round(size_bytes / 1024, 2)
    
    # Medição de Tempo de Leitura
    start_time = time.time()
    _ = read_func(file_path)
    end_time = time.time()
    
    read_time_ms = round((end_time - start_time) * 1000, 2)
    return f"{size_kb} KB", f"{read_time_ms} ms"

print("--- MEDINDO ARQUIVOS NA CAMADA SILVER ---")

p_size, p_time = measure_format("parquet", pd.read_parquet)
c_size, c_time = measure_format("csv", pd.read_csv)
j_size, j_time = measure_format("json", pd.read_json)

print(f"Parquet : Tamanho = {p_size} | Tempo de Leitura = {p_time}")
print(f"CSV     : Tamanho = {c_size} | Tempo de Leitura = {c_time}")
print(f"JSON    : Tamanho = {j_size} | Tempo de Leitura = {j_time}")