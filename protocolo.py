# -*- coding: utf-8 -*-
"""
protocolo.py - Modulo compartilhado para o protocolo NSP (Nuvem Storage Protocol).
Centraliza o empacotamento, envio e recepcao de mensagens e streaming binario.
"""

import os

DELIMITADOR = "|"
TERMINADOR = "\n"
TAMANHO_BLOCO = 4096  # Chunks de 4KB


def enviar_msg(sock, comando, *args):
    """
    Empacota e envia uma mensagem de controle pelo socket TCP.
    Formato: COMANDO|arg1|arg2|...\n
    """
    partes = [str(comando)] + [str(a) for a in args]
    mensagem = DELIMITADOR.join(partes) + TERMINADOR
    sock.sendall(mensagem.encode("utf-8"))


def receber_msg(sock):
    """
    Le bytes do socket um a um ate encontrar o terminador '\\n'.
    Isso garante o framing preciso do protocolo TCP sem ler bytes a mais
    que possam pertencer ao stream binario de arquivos.
    
    Retorna uma lista com as partes da mensagem [COMANDO, arg1, arg2, ...]
    ou None se a conexao for encerrada.
    """
    buffer = bytearray()
    while True:
        try:
            dado = sock.recv(1)
        except (ConnectionResetError, ConnectionAbortedError):
            return None

        if not dado:
            return None
        if dado == b"\n":
            break
        buffer.extend(dado)

    texto = buffer.decode("utf-8", errors="replace")
    if not texto:
        return []
    return texto.split(DELIMITADOR)


def enviar_arquivo(sock, caminho_arquivo, callback_progresso=None):
    """
    Transmite um arquivo local pelo socket em blocos de 4KB.
    Garante que arquivos grandes nao saturem a memoria RAM.
    """
    total_bytes = os.path.getsize(caminho_arquivo)
    bytes_enviados = 0

    with open(caminho_arquivo, "rb") as f:
        while True:
            bloco = f.read(TAMANHO_BLOCO)
            if not bloco:
                break
            sock.sendall(bloco)
            bytes_enviados += len(bloco)
            if callback_progresso:
                callback_progresso(bytes_enviados, total_bytes)


def receber_arquivo(sock, total_bytes, caminho_destino, callback_progresso=None):
    """
    Le exatamente total_bytes do socket em blocos de 4KB e grava no disco.
    Se a conexao cair antes de ler todos os bytes, retorna False.
    """
    restante = total_bytes
    bytes_recebidos = 0

    try:
        with open(caminho_destino, "wb") as f:
            while restante > 0:
                limite = min(TAMANHO_BLOCO, restante)
                bloco = sock.recv(limite)
                if not bloco:
                    # Conexao caiu antes de completar a transmissao
                    return False
                f.write(bloco)
                tamanho_lido = len(bloco)
                restante -= tamanho_lido
                bytes_recebidos += tamanho_lido
                if callback_progresso:
                    callback_progresso(bytes_recebidos, total_bytes)
        return True
    except Exception:
        return False
