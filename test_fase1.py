# -*- coding: utf-8 -*-
"""
test_fase1.py - Testes automatizados para validacao dos requisitos da Fase 1.
Verifica:
1. Fluxo feliz: CONNECT -> WELCOME|OK -> DISCONNECT -> STATUS|OK
2. Violacao de FSM: Envio de comando antes do CONNECT -> STATUS|ERRO
3. Concorrencia: Dois clientes simultaneos autenticando em threads separadas
4. Sistema de arquivos: Criacao de pastas relativas no armazenamento
"""

import os
import time
import socket
import threading
from protocolo import enviar_msg, receber_msg

HOST = "127.0.0.1"
PORTA = 5000


def conectar():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((HOST, PORTA))
    return s


def testar_fluxo_normal():
    print("\n[TESTE 1] Iniciando teste de fluxo normal (CONNECT -> DISCONNECT)...")
    s = conectar()
    try:
        enviar_msg(s, "CONNECT", "usuario_teste1")
        resp = receber_msg(s)
        assert resp is not None, "Servidor nao respondeu ao CONNECT"
        assert resp[0] == "WELCOME" and resp[1] == "OK", f"Resposta inesperada: {resp}"
        print("  -> CONNECT aceito com WELCOME|OK")

        enviar_msg(s, "DISCONNECT")
        resp = receber_msg(s)
        assert resp is not None, "Servidor nao respondeu ao DISCONNECT"
        assert resp[0] == "STATUS" and resp[1] == "OK", f"Resposta inesperada: {resp}"
        print("  -> DISCONNECT aceito com STATUS|OK")
        print("[PASS] Teste 1 concluido com sucesso!")
    finally:
        s.close()


def testar_violacao_fsm():
    print("\n[TESTE 2] Iniciando teste de violacao da FSM (comando antes do CONNECT)...")
    s = conectar()
    try:
        # Envia LIST_REQ sem autenticar
        enviar_msg(s, "LIST_REQ")
        resp = receber_msg(s)
        assert resp is not None, "Servidor nao respondeu a violacao de FSM"
        assert resp[0] == "STATUS" and resp[1] == "ERRO", f"Resposta inesperada: {resp}"
        print(f"  -> Servidor bloqueou comando com: {resp}")

        # Tenta ler novamente para garantir que o servidor fechou a conexao
        fim = receber_msg(s)
        assert fim is None, "Servidor deveria ter fechado a conexao apos violacao"
        print("  -> Servidor encerrou o socket do cliente indisciplinado conforme esperado")
        print("[PASS] Teste 2 concluido com sucesso!")
    finally:
        s.close()


def testar_concorrencia():
    print("\n[TESTE 3] Iniciando teste de conexoes simultaneas (2 clientes em paralelo)...")
    sucessos = []

    def cliente_concorrente(nome):
        try:
            s = conectar()
            enviar_msg(s, "CONNECT", nome)
            resp = receber_msg(s)
            if resp and resp[0] == "WELCOME" and resp[1] == "OK":
                time.sleep(0.5)  # Mantem ambos conectados ao mesmo tempo
                enviar_msg(s, "DISCONNECT")
                resp_disc = receber_msg(s)
                if resp_disc and resp_disc[0] == "STATUS" and resp_disc[1] == "OK":
                    sucessos.append(nome)
            s.close()
        except Exception as e:
            print(f"  [ERRO] Falha no cliente {nome}: {e}")

    t1 = threading.Thread(target=cliente_concorrente, args=("cliente_alpha",))
    t2 = threading.Thread(target=cliente_concorrente, args=("cliente_beta",))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert "cliente_alpha" in sucessos, "cliente_alpha nao completou com sucesso"
    assert "cliente_beta" in sucessos, "cliente_beta nao completou com sucesso"
    print("  -> Ambos os clientes conectaram, autenticaram e desconectaram em paralelo!")
    print("[PASS] Teste 3 concluido com sucesso!")


def testar_pastas():
    print("\n[TESTE 4] Verificando criacao automatica de pastas relativas no disco...")
    pastas_esperadas = ["usuario_teste1", "cliente_alpha", "cliente_beta"]
    for pasta in pastas_esperadas:
        caminho = os.path.join("armazenamento", pasta)
        assert os.path.isdir(caminho), f"Pasta esperada '{caminho}' nao foi criada!"
        print(f"  -> Pasta confirmada no disco: {caminho}")
    print("[PASS] Teste 4 concluido com sucesso!")


if __name__ == "__main__":
    print("=" * 60)
    print("   BATERIA DE TESTES AUTOMATIZADOS - FASE 1")
    print("=" * 60)
    testar_fluxo_normal()
    testar_violacao_fsm()
    testar_concorrencia()
    testar_pastas()
    print("\n" + "=" * 60)
    print("   TODOS OS 4 TESTES DA FASE 1 FORAM APROVADOS COM SUCESSO!")
    print("=" * 60)
