# -*- coding: utf-8 -*-
"""
test_fase2.py - Bateria de testes automatizados para a Fase 2 (Upload de Arquivos).
Verifica:
1. Upload de arquivo de texto pequeno com comparacao de hash MD5.
2. Upload de arquivo binario (50KB de dados aleatorios) com comparacao de hash MD5.
3. Upload de arquivo vazio (0 bytes) para garantir que nao trava.
4. Upload de arquivo com espacos no nome.
5. Queda abrupta do cliente no meio da transmissao (servidor deve descartar o arquivo parcial).
"""

import os
import time
import socket
import hashlib
from protocolo import enviar_msg, receber_msg, enviar_arquivo

HOST = "127.0.0.1"
PORTA = 5000
USUARIO_TESTE = "testador_fase2"


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


def testar_upload_texto():
    print("\n[TESTE 1] Upload de arquivo de texto pequeno...")
    nome = "mensagem_teste.txt"
    conteudo = "Ola, este e um teste de upload para a nuvem pessoal em Python!\nRedes de Computadores 2026."
    caminho_local = f"local_{nome}"

    with open(caminho_local, "w", encoding="utf-8") as f:
        f.write(conteudo)

    md5_origem = calcular_md5(caminho_local)
    tamanho = os.path.getsize(caminho_local)

    s = conectar_e_autenticar()
    try:
        enviar_msg(s, "UPLOAD_REQ", nome, tamanho)
        resp = receber_msg(s)
        assert resp and resp[0] == "STATUS" and resp[1] == "OK", f"Servidor recusou upload: {resp}"

        enviar_arquivo(s, caminho_local)
        ack = receber_msg(s)
        assert ack == ["STATUS", "OK", "recebido"], f"Servidor nao confirmou o upload: {ack}"

        caminho_servidor = os.path.join("armazenamento", USUARIO_TESTE, nome)
        assert os.path.isfile(caminho_servidor), "Arquivo nao foi salvo no servidor!"
        md5_destino = calcular_md5(caminho_servidor)
        assert md5_origem == md5_destino, f"Hashes MD5 divergem! Origem: {md5_origem}, Servidor: {md5_destino}"
        print(f"  -> Sucesso! Hashes MD5 conferem perfeitamente ({md5_origem})")
        print("[PASS] Teste 1 concluido!")
    finally:
        s.close()
        if os.path.exists(caminho_local):
            os.remove(caminho_local)


def testar_upload_binario():
    print("\n[TESTE 2] Upload de arquivo binario bruto (50 KB de dados aleatorios)...")
    nome = "dados_binarios.bin"
    caminho_local = f"local_{nome}"
    tamanho_bytes = 51200  # 50 KB

    # Gera 50KB de bytes aleatorios (simulando imagem/video)
    dados = os.urandom(tamanho_bytes)
    with open(caminho_local, "wb") as f:
        f.write(dados)

    md5_origem = calcular_md5(caminho_local)

    s = conectar_e_autenticar()
    try:
        enviar_msg(s, "UPLOAD_REQ", nome, tamanho_bytes)
        resp = receber_msg(s)
        assert resp and resp[0] == "STATUS" and resp[1] == "OK", f"Servidor recusou upload: {resp}"

        enviar_arquivo(s, caminho_local)
        ack = receber_msg(s)
        assert ack == ["STATUS", "OK", "recebido"], f"Servidor nao confirmou o upload: {ack}"

        caminho_servidor = os.path.join("armazenamento", USUARIO_TESTE, nome)
        assert os.path.isfile(caminho_servidor), "Arquivo binario nao foi salvo no servidor!"
        assert os.path.getsize(caminho_servidor) == tamanho_bytes, "Tamanho em bytes difere do original!"
        md5_destino = calcular_md5(caminho_servidor)
        assert md5_origem == md5_destino, f"Hashes MD5 divergem no binario!"
        print(f"  -> Sucesso! 50KB binarios gravados com integridade bit a bit ({md5_origem})")
        print("[PASS] Teste 2 concluido!")
    finally:
        s.close()
        if os.path.exists(caminho_local):
            os.remove(caminho_local)


def testar_upload_arquivo_vazio():
    print("\n[TESTE 3] Upload de arquivo vazio (0 bytes)...")
    nome = "arquivo_vazio.txt"
    caminho_local = f"local_{nome}"

    with open(caminho_local, "wb") as f:
        pass  # Arquivo de 0 bytes

    s = conectar_e_autenticar()
    try:
        enviar_msg(s, "UPLOAD_REQ", nome, 0)
        resp = receber_msg(s)
        assert resp and resp[0] == "STATUS" and resp[1] == "OK", f"Servidor recusou arquivo vazio: {resp}"

        enviar_arquivo(s, caminho_local)
        ack = receber_msg(s)
        assert ack == ["STATUS", "OK", "recebido"], f"Servidor nao confirmou o upload: {ack}"

        caminho_servidor = os.path.join("armazenamento", USUARIO_TESTE, nome)
        assert os.path.isfile(caminho_servidor), "Arquivo de 0 bytes nao foi criado!"
        assert os.path.getsize(caminho_servidor) == 0, "Arquivo deveria ter tamanho 0!"
        print("  -> Sucesso! Servidor tratou arquivo de 0 bytes sem travar o socket")
        print("[PASS] Teste 3 concluido!")
    finally:
        s.close()
        if os.path.exists(caminho_local):
            os.remove(caminho_local)


def testar_upload_nome_com_espacos():
    print("\n[TESTE 4] Upload de arquivo com espacos no nome...")
    nome = "relatorio final redes 2026 versao 1.pdf"
    caminho_local = f"local_{nome}"
    conteudo = b"%PDF-1.4 Simulado para Teste de Redes com Espacos"

    with open(caminho_local, "wb") as f:
        f.write(conteudo)

    tamanho = len(conteudo)
    s = conectar_e_autenticar()
    try:
        enviar_msg(s, "UPLOAD_REQ", nome, tamanho)
        resp = receber_msg(s)
        assert resp and resp[0] == "STATUS" and resp[1] == "OK", f"Servidor recusou nome com espacos: {resp}"

        enviar_arquivo(s, caminho_local)
        ack = receber_msg(s)
        assert ack == ["STATUS", "OK", "recebido"], f"Servidor nao confirmou o upload: {ack}"

        caminho_servidor = os.path.join("armazenamento", USUARIO_TESTE, nome)
        assert os.path.isfile(caminho_servidor), f"Arquivo '{nome}' nao foi salvo corretamente!"
        print(f"  -> Sucesso! O delimitador pipe protegeu o nome com espacos perfeitamente.")
        print("[PASS] Teste 4 concluido!")
    finally:
        s.close()
        if os.path.exists(caminho_local):
            os.remove(caminho_local)


def testar_queda_abrupta_upload():
    print("\n[TESTE 5] Queda abrupta do cliente no meio da transmissao...")
    nome = "arquivo_interrompido.bin"
    tamanho_total = 65536  # 64 KB
    caminho_servidor = os.path.join("armazenamento", USUARIO_TESTE, nome)

    if os.path.exists(caminho_servidor):
        os.remove(caminho_servidor)

    s = conectar_e_autenticar()
    try:
        enviar_msg(s, "UPLOAD_REQ", nome, tamanho_total)
        resp = receber_msg(s)
        assert resp and resp[0] == "STATUS" and resp[1] == "OK"

        # Envia apenas 4KB e mata o socket abruptamente
        s.sendall(os.urandom(4096))
        s.close()
        print("  -> Cliente encerrou o socket de surpresa apos enviar apenas 4KB de 64KB...")

        time.sleep(0.5)  # Tempo para o servidor detectar a queda e fazer cleanup

        # O servidor deve ter descartado o arquivo parcial
        assert not os.path.exists(caminho_servidor), "Arquivo parcial nao foi removido pelo servidor apos a queda!"
        print("  -> Sucesso! Servidor detectou desconexao e expurgou o arquivo corrompido/parcial.")
        print("[PASS] Teste 5 concluido!")
    except Exception as e:
        print(f"[ERRO] Falha no teste de queda abrupta: {e}")
        raise


if __name__ == "__main__":
    print("=" * 60)
    print("   BATERIA DE TESTES AUTOMATIZADOS - FASE 2 (UPLOAD)")
    print("=" * 60)
    testar_upload_texto()
    testar_upload_binario()
    testar_upload_arquivo_vazio()
    testar_upload_nome_com_espacos()
    testar_queda_abrupta_upload()
    print("\n" + "=" * 60)
    print("   TODOS OS 5 TESTES DA FASE 2 FORAM APROVADOS COM SUCESSO!")
    print("=" * 60)
