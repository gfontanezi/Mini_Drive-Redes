# -*- coding: utf-8 -*-
"""
test_keepalive.py - Testes do keep-alive (PING/PONG) e da confirmacao de upload.

Sobe o proprio servidor em uma thread (porta 5055) com tempos reduzidos para
o teste nao demorar: PING a cada 1s e timeout de 3s. Basta executar:

    python test_keepalive.py

Verifica:
1. PING|<seq> e respondido com PONG|<seq>
2. PING antes do CONNECT e bloqueado pela maquina de estados
3. Cliente que para de mandar mensagens e derrubado pelo servidor
4. Cliente que manda PING regularmente continua conectado
5. A thread de keep-alive do cliente mantem a sessao viva sozinha
6. PING nao se mistura com os bytes de um upload (trava) e o upload e confirmado
"""

import os
import time
import socket
import hashlib
import threading

import servidor
import cliente
from protocolo import enviar_msg, receber_msg

HOST = "127.0.0.1"
PORTA = 5055

# Tempos reduzidos so para o teste
servidor.TIMEOUT_KEEPALIVE = 3
cliente.INTERVALO_KEEPALIVE = 1
cliente.TIMEOUT_KEEPALIVE = 3


def subir_servidor():
    threading.Thread(target=servidor.iniciar_servidor, kwargs={"host": HOST, "porta": PORTA}, daemon=True).start()
    time.sleep(0.5)


def conectar_e_autenticar(usuario):
    s = socket.create_connection((HOST, PORTA))
    s.settimeout(10)
    enviar_msg(s, "CONNECT", usuario)
    assert receber_msg(s)[1] == "OK"
    return s


def md5(caminho):
    with open(caminho, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def teste_1_ping_pong():
    print("\n[TESTE 1] PING|<seq> -> PONG|<seq>...")
    s = conectar_e_autenticar("ka_user")
    for seq in (1, 2, 3):
        inicio = time.time()
        enviar_msg(s, "PING", seq)
        resp = receber_msg(s)
        assert resp == ["PONG", str(seq)], resp
        print(f"  -> PING|{seq} => PONG|{resp[1]} (RTT {(time.time() - inicio) * 1000:.2f} ms)")
    s.close()
    print("[PASS] Teste 1")


def teste_2_ping_sem_login():
    print("\n[TESTE 2] PING antes do CONNECT...")
    s = socket.create_connection((HOST, PORTA))
    enviar_msg(s, "PING", 1)
    resp = receber_msg(s)
    assert resp[0] == "STATUS" and resp[1] == "ERRO", resp
    assert receber_msg(s) is None, "Servidor deveria ter fechado a conexao"
    print(f"  -> Bloqueado com {'|'.join(resp)} e conexao fechada")
    print("[PASS] Teste 2")


def teste_3_cliente_mudo():
    print("\n[TESTE 3] Cliente que para de mandar mensagens (timeout = 3s)...")
    s = conectar_e_autenticar("cliente_mudo")
    inicio = time.time()
    resp = receber_msg(s)            # nao envia nada, so espera o servidor agir
    decorrido = time.time() - inicio
    assert resp is None, f"Esperava conexao fechada, veio {resp}"
    assert 2.8 <= decorrido <= 4, f"Derrubado em {decorrido:.2f}s"
    print(f"  -> Servidor fechou a conexao apos {decorrido:.2f}s sem receber nada")
    s.close()
    print("[PASS] Teste 3")


def teste_4_cliente_vivo():
    print("\n[TESTE 4] Cliente que manda PING a cada 2s, por 7s...")
    s = conectar_e_autenticar("cliente_vivo")
    for seq in range(1, 4):
        time.sleep(2)
        enviar_msg(s, "PING", seq)
        assert receber_msg(s) == ["PONG", str(seq)]
    enviar_msg(s, "LIST_REQ")
    assert receber_msg(s)[0] == "LIST_RESP"
    print("  -> Continua conectado (LIST_REQ respondido normalmente)")
    s.close()
    print("[PASS] Teste 4")


def teste_5_thread_do_cliente():
    print("\n[TESTE 5] Thread de keep-alive do cliente, 5s parado...")
    s = conectar_e_autenticar("cliente_thread")
    s.settimeout(cliente.TIMEOUT_KEEPALIVE)
    sessao = cliente.Sessao(s)
    sessao.iniciar_keepalive()
    time.sleep(5)                    # bem mais que os 3s de timeout do servidor
    assert sessao.ativa and sessao.seq >= 3, (sessao.ativa, sessao.seq)
    sessao.ativa = False
    with sessao.trava:
        enviar_msg(s, "DISCONNECT")
        resp = receber_msg(s)
    assert resp[0] == "STATUS" and resp[1] == "OK", resp
    print(f"  -> {sessao.seq} PINGs enviados, ultimo RTT {sessao.ultimo_rtt_ms:.2f} ms; DISCONNECT OK")
    s.close()
    print("[PASS] Teste 5")


def teste_6_ping_durante_upload():
    print("\n[TESTE 6] Upload lento (~3s) com a thread de PING rodando...")
    origem = "temp_upload_keepalive.bin"
    with open(origem, "wb") as f:
        f.write(os.urandom(4 * 1024 * 1024))   # 4 MB

    # Deixa o envio mais lento para garantir que o PING "queira" entrar no meio
    enviar_original = cliente.enviar_arquivo
    cliente.enviar_arquivo = lambda sock, caminho, callback_progresso=None: \
        enviar_original(sock, caminho, callback_progresso=lambda enviados, total: time.sleep(0.003))

    s = conectar_e_autenticar("cliente_upload")
    s.settimeout(cliente.TIMEOUT_KEEPALIVE)
    sessao = cliente.Sessao(s)
    sessao.iniciar_keepalive()
    try:
        inicio = time.time()
        with sessao.trava:
            confirmado = cliente.executar_upload_rede(s, origem, os.path.basename(origem), os.path.getsize(origem))
        assert confirmado, "Servidor nao confirmou o upload"
        duracao = time.time() - inicio
        pings_apos_upload = sessao.seq
        time.sleep(2.5)
        assert sessao.ativa and sessao.seq > pings_apos_upload, "Keep-alive parou depois do upload"

        destino = os.path.join(servidor.PASTA_ARMAZENAMENTO, "cliente_upload", origem)
        assert md5(origem) == md5(destino), "Arquivo corrompido: o PING entrou no meio dos bytes!"
        print(f"  -> Upload levou {duracao:.1f}s (mais que o intervalo de 1s); MD5 identico")
        print(f"  -> Servidor confirmou o upload e os PINGs continuaram depois ({sessao.seq} no total)")
    finally:
        sessao.ativa = False
        cliente.enviar_arquivo = enviar_original
        s.close()
        os.remove(origem)
    print("[PASS] Teste 6")


if __name__ == "__main__":
    print("=" * 60)
    print("   TESTES DO KEEP-ALIVE (PING/PONG)")
    print("=" * 60)
    subir_servidor()
    testes = [teste_1_ping_pong, teste_2_ping_sem_login, teste_3_cliente_mudo,
              teste_4_cliente_vivo, teste_5_thread_do_cliente, teste_6_ping_durante_upload]
    for teste in testes:
        teste()
    print("\n" + "=" * 60)
    print(f"   TODOS OS {len(testes)} TESTES PASSARAM!")
    print("=" * 60)
