# TTS Experiments 🎙️

Este repositório é um laboratório de testes para geração de áudio a partir de texto (Text-to-Speech). O objetivo inicial foi criar uma prova de conceito simples e funcional para automatizar a leitura de arquivos `.txt` extensos (como artigos acadêmicos) e transformá-los em `.mp3`.

## 🛠️ O que foi feito até agora
A primeira iteração utiliza a biblioteca `edge-tts`, que consome a API de vozes neurais da Microsoft. É uma solução rápida, leve no processamento local e com vozes altamente naturais (como a *FranciscaNeural* para PT-BR).

**Funcionalidades:**
- Leitura automatizada de arquivos `.txt`.
- Geração direta de arquivos `.mp3` no mesmo diretório.
- Processamento assíncrono para lidar com grandes blocos de texto.

## 🚀 Como rodar

1. Clone o repositório e crie um ambiente virtual:
   ```bash
    python -m venv venv
   .\venv\Scripts\activate
   ```

2. Instale as dependências:
```Bash
    pip install edge-tts
```

3. Execute o script:
```Bash
python leitor.py
```

4. Insira o caminho do arquivo de texto quando solicitado. O áudio será gerado na mesma pasta.

## 🗺️ Próximos Passos (Roadmap)
- [ ] **Desacoplar da nuvem:** Substituir o `edge-tts` por um modelo de inferência 100% offline e local (como o **Piper TTS**).
- [ ] Adicionar suporte a múltiplos idiomas e seleção dinâmica de vozes.
- [ ] Implementar quebra automática de texto para contornar limites de requisição em arquivos massivos.

---
*Criado como um teste rápido para explorar automação e manipulação de mídia em Python.*