# -*- coding: utf-8 -*-
"""
test_fase3.py - Bateria de testes automatizados para a Fase 3 (Listagem e Download).
Verifica:
1. Listagem de pasta vazia (LIST_RESP|0|)
2. Listagem com multiplos arquivos e conferencia de nomes e tamanhos
3. Download de arquivo binario existente com verificacao de hash MD5 idêntico
4. Download de arquivo inexistente (resposta STATUS|ERRO sem travar)
5. Download de arquivo de 0 bytes
"""

import os
import time
import socket
import hashlib
from protocolo import enviar_msg, receber_msg, enviar_arquivo, receber_arquivo

HOST = "127.0.0.1"
PORTA = 5000
USUARIO_TESTE = "testador_fase3"
PASTA_TEMP_DOWNLOADS = "temp_test_downloads"


def calcular_md5(caminho):
    hasher = hashlib.md5()
    with open(caminho, "rb") as f:
        while True:
            chunk = f.read(4096)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def conectar_e_autenticar(usuario=USUARIO_TESTE):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((HOST, PORTA))
    enviar_msg(s, "CONNECT", usuario)
    resp = receber_msg(s)
    assert resp and resp[0] == "WELCOME" and resp[1] == "OK", f"Falha no login: {resp}"
    return s


def testar_list_pasta_vazia():
    print("\n[TESTE 1] Listagem de pasta vazia...")
    usuario_limpo = "usuario_sem_arquivos"
    # Garante que a pasta esta limpa
    pasta = os.path.join("armazenamento", usuario_limpo)
    if os.path.exists(pasta):
        for f in os.listdir(pasta):
            os.remove(os.path.join(pasta, f))

    s = conectar_e_autenticar(usuario_limpo)
    try:
        enviar_msg(s, "LIST_REQ")
        resp = receber_msg(s)
        assert resp and resp[0] == "LIST_RESP", f"Resposta invalida para LIST_REQ: {resp}"
        total = int(resp[1])
        assert total == 0, f"Esperava 0 arquivos, mas recebeu: {total}"
        print("  -> Sucesso! Servidor respondeu LIST_RESP com 0 arquivos.")
        print("[PASS] Teste 1 concluido!")
    finally:
        s.close()


def testar_list_com_multiplos_arquivos():
    print("\n[TESTE 2] Listagem com múltiplos arquivos...")
    s = conectar_e_autenticar()
    try:
        # Envia 3 arquivos com tamanhos conhecidos
        arquivos = [
            ("nota1.txt", b"A" * 150),
            ("nota2.txt", b"B" * 250),
            ("planilha.csv", b"C" * 400),
        ]
        for nome, dados in arquivos:
            enviar_msg(s, "UPLOAD_REQ", nome, len(dados))
            resp = receber_msg(s)
            assert resp and resp[0] == "STATUS" and resp[1] == "OK"
            s.sendall(dados)
            assert receber_msg(s) == ["STATUS", "OK", "recebido"]

        # Solicita listagem
        enviar_msg(s, "LIST_REQ")
        resp = receber_msg(s)
        assert resp and resp[0] == "LIST_RESP"
        total = int(resp[1])
        assert total >= 3, f"Esperava pelo menos 3 arquivos, recebeu: {total}"
        dados_str = resp[2] if len(resp) > 2 else ""

        for nome, dados in arquivos:
            esperado = f"{nome}:{len(dados)}"
            assert esperado in dados_str, f"Arquivo {esperado} nao encontrado em {dados_str}"
            print(f"  -> Arquivo confirmado na listagem remota: {nome} ({len(dados)} bytes)")

        print("[PASS] Teste 2 concluido!")
    finally:
        s.close()


def testar_download_arquivo_existente():
    print("\n[TESTE 3] Download de arquivo existente com checagem de hash MD5...")
    os.makedirs(PASTA_TEMP_DOWNLOADS, exist_ok=True)
    nome = "foto_alta_resolucao.bin"
    conteudo_binario = os.urandom(32768)  # 32 KB
    caminho_origem = os.path.join(PASTA_TEMP_DOWNLOADS, f"origem_{nome}")
    caminho_destino = os.path.join(PASTA_TEMP_DOWNLOADS, f"baixado_{nome}")

    with open(caminho_origem, "wb") as f:
        f.write(conteudo_binario)

    md5_esperado = calcular_md5(caminho_origem)

    s = conectar_e_autenticar()
    try:
        # Faz upload primeiro
        enviar_msg(s, "UPLOAD_REQ", nome, len(conteudo_binario))
        resp = receber_msg(s)
        assert resp and resp[0] == "STATUS" and resp[1] == "OK"
        enviar_arquivo(s, caminho_origem)
        assert receber_msg(s) == ["STATUS", "OK", "recebido"]

        # Agora realiza o download do mesmo arquivo
        enviar_msg(s, "DOWNLOAD_REQ", nome)
        resp_down = receber_msg(s)
        assert resp_down and resp_down[0] == "STATUS" and resp_down[1] == "OK", f"Servidor recusou download: {resp_down}"

        tamanho_declarado = int(resp_down[2])
        assert tamanho_declarado == len(conteudo_binario), "Tamanho informado pelo servidor difere do real!"

        sucesso = receber_arquivo(s, tamanho_declarado, caminho_destino)
        assert sucesso, "Falha na recepcao dos bytes do download!"

        md5_baixado = calcular_md5(caminho_destino)
        assert md5_esperado == md5_baixado, f"MD5 divergiu! Origem: {md5_esperado}, Baixado: {md5_baixado}"
        print(f"  -> Sucesso absoluto! Hash MD5 do arquivo baixado confere: {md5_baixado}")
        print("[PASS] Teste 3 concluido!")
    finally:
        s.close()
        for p in [caminho_origem, caminho_destino]:
            if os.path.exists(p):
                os.remove(p)


def testar_download_inexistente():
    print("\n[TESTE 4] Tentativa de download de arquivo inexistente...")
    s = conectar_e_autenticar()
    try:
        enviar_msg(s, "DOWNLOAD_REQ", "arquivo_fantasma_inexistente.pdf")
        resp = receber_msg(s)
        assert resp and resp[0] == "STATUS" and resp[1] == "ERRO", f"Resposta inesperada para inexistente: {resp}"
        print(f"  -> Sucesso! Servidor respondeu amigavelmente com: {resp[2]}")
        print("[PASS] Teste 4 concluido!")
    finally:
        s.close()


def testar_download_arquivo_vazio():
    print("\n[TESTE 5] Download de arquivo vazio (0 bytes)...")
    nome = "zero_bytes.txt"
    s = conectar_e_autenticar()
    try:
        # Sobe arquivo vazio
        enviar_msg(s, "UPLOAD_REQ", nome, 0)
        assert receber_msg(s)[1] == "OK"
        assert receber_msg(s) == ["STATUS", "OK", "recebido"]

        # Baixa arquivo vazio
        enviar_msg(s, "DOWNLOAD_REQ", nome)
        resp = receber_msg(s)
        assert resp and resp[0] == "STATUS" and resp[1] == "OK" and int(resp[2]) == 0

        caminho_dest = os.path.join(PASTA_TEMP_DOWNLOADS, f"baixado_{nome}")
        sucesso = receber_arquivo(s, 0, caminho_dest)
        assert sucesso and os.path.isfile(caminho_dest) and os.path.getsize(caminho_dest) == 0
        print("  -> Sucesso! Arquivo de 0 bytes baixado perfeitamente sem travar.")
        print("[PASS] Teste 5 concluido!")
    finally:
        s.close()
        if os.path.exists(caminho_dest):
            os.remove(caminho_dest)


if __name__ == "__main__":
    print("=" * 60)
    print("   BATERIA DE TESTES AUTOMATIZADOS - FASE 3 (LIST & DOWNLOAD)")
    print("=" * 60)
    testar_list_pasta_vazia()
    testar_list_com_multiplos_arquivos()
    testar_download_arquivo_existente()
    testar_download_inexistente()
    testar_download_arquivo_vazio()
    print("\n" + "=" * 60)
    print("   TODOS OS 5 TESTES DA FASE 3 FORAM APROVADOS COM SUCESSO!")
    print("=" * 60)
