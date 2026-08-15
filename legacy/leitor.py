import asyncio
import edge_tts
from pathlib import Path

async def principal():
    # 1. Pede o caminho do arquivo (o strip remove aspas caso você use "Copiar como caminho" no Windows)
    caminho_txt = input("Cole o caminho do arquivo .txt: ").strip('"\' ')
    arquivo = Path(caminho_txt)

    # 2. Verifica se o arquivo existe
    if not arquivo.is_file():
        print("Erro: Arquivo não encontrado.")
        return

    # 3. Lê o texto e define o nome de saída trocando .txt por .mp3
    texto = arquivo.read_text(encoding="utf-8")
    caminho_mp3 = arquivo.with_suffix(".mp3")

    # 4. Gera e salva o áudio
    print(f"Lendo texto e gerando áudio em: {caminho_mp3} ...")
    #await edge_tts.Communicate(texto, "pt-BR-FranciscaNeural").save(str(caminho_mp3)) # Texto em Portugues
    await edge_tts.Communicate(texto, "en-US-AriaNeural").save(str(caminho_mp3)) # Texto em Ingles
    print("Concluído!")

if __name__ == "__main__":
    asyncio.run(principal())