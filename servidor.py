# -*- coding: utf-8 -*-
"""
servidor.py - Servidor TCP Multithread para a Mini Nuvem Pessoal.
Disciplina: Redes de Computadores
Protocolo: NSP (Nuvem Storage Protocol)
"""

import os
import sys
import socket
import threading
from protocolo import enviar_msg, receber_msg, receber_arquivo, enviar_arquivo, TIMEOUT_KEEPALIVE

HOST_PADRAO = "0.0.0.0"
PORTA_PADRAO = 5000
PASTA_ARMAZENAMENTO = "armazenamento"


def tratar_cliente(conn, addr):
    """
    Funcao executada em uma thread separada para cada cliente conectado.
    Gerencia a conexao, a Maquina de Estados Finita (FSM) e todas as operacoes.
    """
    ip_porta = f"{addr[0]}:{addr[1]}"
    nome_thread = threading.current_thread().name
    print(f"[+] [{nome_thread}] Conexao estabelecida de {ip_porta}")

    estado = "NAO_AUTENTICADO"
    usuario = None

    try:
        while True:
            try:
                partes = receber_msg(conn)
            except socket.timeout:
                # Passou TIMEOUT_KEEPALIVE segundos sem chegar nenhum byte:
                # o cliente parou de mandar PING, entao consideramos que caiu.
                print(f"[KEEPALIVE] [{nome_thread}] '{usuario}' ficou {TIMEOUT_KEEPALIVE}s sem enviar nada. Encerrando conexao.")
                break

            if partes is None:
                print(f"[-] [{nome_thread}] Conexao encerrada pelo cliente {ip_porta}")
                break

            if not partes:
                continue

            comando = partes[0]

            # -----------------------------------------------------------------
            # ESTADO 1: NAO_AUTENTICADO
            # -----------------------------------------------------------------
            if estado == "NAO_AUTENTICADO":
                if comando == "CONNECT":
                    if len(partes) < 2 or not partes[1].strip():
                        print(f"[!] [{nome_thread}] Tentativa de CONNECT sem usuario de {ip_porta}")
                        enviar_msg(conn, "WELCOME", "ERRO", "Nome de usuario invalido ou vazio")
                        break

                    usuario = partes[1].strip()
                    caminho_usuario = os.path.join(PASTA_ARMAZENAMENTO, usuario)
                    os.makedirs(caminho_usuario, exist_ok=True)

                    estado = "AUTENTICADO"
                    # A partir do login, o recv() passa a ter prazo: se o cliente
                    # ficar TIMEOUT_KEEPALIVE segundos mudo, levanta socket.timeout.
                    conn.settimeout(TIMEOUT_KEEPALIVE)
                    print(f"[AUTH] [{nome_thread}] Usuario '{usuario}' autenticado! Pasta: '{caminho_usuario}'")
                    enviar_msg(conn, "WELCOME", "OK", f"Bem-vindo {usuario}")

                else:
                    print(f"[VIOLACAO FSM] [{nome_thread}] Comando '{comando}' rejeitado de {ip_porta}: login necessario.")
                    enviar_msg(conn, "STATUS", "ERRO", "Autenticacao necessaria")
                    break

            # -----------------------------------------------------------------
            # ESTADO 2: AUTENTICADO
            # -----------------------------------------------------------------
            elif estado == "AUTENTICADO":
                pasta_usuario = os.path.join(PASTA_ARMAZENAMENTO, usuario)

                # -------------------------------------------------------------
                # KEEP-ALIVE: responde PING|<seq> com PONG|<seq>
                # -------------------------------------------------------------
                if comando == "PING":
                    seq = partes[1] if len(partes) > 1 else ""
                    print(f"[KEEPALIVE] [{nome_thread}] PING #{seq} de '{usuario}' -> PONG")
                    enviar_msg(conn, "PONG", seq)

                elif comando == "DISCONNECT":
                    print(f"[-] [{nome_thread}] Desconexao graciosa do usuario '{usuario}' ({ip_porta})")
                    enviar_msg(conn, "STATUS", "OK", "Ate logo")
                    estado = "FINALIZADO"
                    break

                # -------------------------------------------------------------
                # OPERACAO: UPLOAD
                # -------------------------------------------------------------
                elif comando == "UPLOAD_REQ":
                    if len(partes) < 3:
                        enviar_msg(conn, "STATUS", "ERRO", "Parametros insuficientes para UPLOAD_REQ")
                        continue

                    nome_arquivo = os.path.basename(partes[1].strip())
                    if not nome_arquivo:
                        enviar_msg(conn, "STATUS", "ERRO", "Nome de arquivo invalido")
                        continue

                    try:
                        tamanho_bytes = int(partes[2])
                        if tamanho_bytes < 0:
                            raise ValueError
                    except ValueError:
                        enviar_msg(conn, "STATUS", "ERRO", "Tamanho de arquivo deve ser um inteiro positivo")
                        continue

                    caminho_destino = os.path.join(pasta_usuario, nome_arquivo)
                    print(f"[*] [{nome_thread}] Autorizando upload de '{nome_arquivo}' ({tamanho_bytes} bytes)...")
                    enviar_msg(conn, "STATUS", "OK", "pronto")

                    sucesso = receber_arquivo(conn, tamanho_bytes, caminho_destino)
                    if sucesso:
                        print(f"[UPLOAD] [{nome_thread}] Arquivo '{nome_arquivo}' ({tamanho_bytes} bytes) salvo com sucesso!")
                        # Confirma ao cliente que recebeu todos os bytes (ACK do upload)
                        enviar_msg(conn, "STATUS", "OK", "recebido")
                    else:
                        print(f"[!] [{nome_thread}] Falha na transmissao de '{nome_arquivo}'. Descartando arquivo parcial.")
                        if os.path.exists(caminho_destino):
                            try:
                                os.remove(caminho_destino)
                            except OSError:
                                pass
                        break

                # -------------------------------------------------------------
                # OPERACAO: LISTAGEM REMOTA
                # -------------------------------------------------------------
                elif comando == "LIST_REQ":
                    print(f"[*] [{nome_thread}] Listando arquivos do usuario '{usuario}'...")
                    if not os.path.exists(pasta_usuario):
                        enviar_msg(conn, "LIST_RESP", 0, "")
                        continue

                    itens = []
                    for item in os.listdir(pasta_usuario):
                        caminho_completo = os.path.join(pasta_usuario, item)
                        if os.path.isfile(caminho_completo):
                            tam = os.path.getsize(caminho_completo)
                            itens.append(f"{item}:{tam}")

                    quantidade = len(itens)
                    dados_formatados = ";".join(itens)
                    print(f"[LIST] [{nome_thread}] Retornando {quantidade} arquivos para '{usuario}'.")
                    # Formato: LIST_RESP|<quantidade>|<nome1:tam1;nome2:tam2;...>
                    enviar_msg(conn, "LIST_RESP", quantidade, dados_formatados)

                # -------------------------------------------------------------
                # OPERACAO: DOWNLOAD
                # -------------------------------------------------------------
                elif comando == "DOWNLOAD_REQ":
                    if len(partes) < 2 or not partes[1].strip():
                        enviar_msg(conn, "STATUS", "ERRO", "Nome do arquivo nao especificado")
                        continue

                    nome_arquivo = os.path.basename(partes[1].strip())
                    caminho_arquivo = os.path.join(pasta_usuario, nome_arquivo)

                    if not os.path.isfile(caminho_arquivo):
                        print(f"[!] [{nome_thread}] Arquivo '{nome_arquivo}' solicitado para download nao existe.")
                        enviar_msg(conn, "STATUS", "ERRO", "Arquivo nao encontrado")
                        continue

                    tamanho_bytes = os.path.getsize(caminho_arquivo)
                    print(f"[*] [{nome_thread}] Autorizando download de '{nome_arquivo}' ({tamanho_bytes} bytes)...")
                    
                    # Avisa o cliente que o arquivo existe e seu tamanho exato
                    enviar_msg(conn, "STATUS", "OK", tamanho_bytes)

                    # Transmite os bytes do arquivo em blocos de 4KB
                    try:
                        enviar_arquivo(conn, caminho_arquivo)
                        print(f"[DOWNLOAD] [{nome_thread}] Arquivo '{nome_arquivo}' transmitido com sucesso para '{usuario}'!")
                    except Exception as e:
                        print(f"[ERRO] [{nome_thread}] Queda durante envio de '{nome_arquivo}': {e}")
                        break

                else:
                    print(f"[!] [{nome_thread}] Comando desconhecido '{comando}' de {ip_porta}")
                    enviar_msg(conn, "STATUS", "ERRO", f"Comando desconhecido '{comando}'")

    except Exception as e:
        print(f"[ERRO] [{nome_thread}] Erro na sessao de {ip_porta}: {e}")
    finally:
        conn.close()
        print(f"[*] [{nome_thread}] Socket de {ip_porta} encerrado e recursos liberados.")


def iniciar_servidor(host=HOST_PADRAO, porta=PORTA_PADRAO):
    """
    Inicializa o socket TCP do servidor e o loop de aceitacao com Threads.
    """
    os.makedirs(PASTA_ARMAZENAMENTO, exist_ok=True)

    servidor_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        servidor_sock.bind((host, porta))
        servidor_sock.listen(10)
        print("=" * 60)
        print("   MINI NUVEM PESSOAL - SERVIDOR TCP INICIADO")
        print(f"   Escutando em: {host}:{porta}")
        print(f"   Pasta de armazenamento: ./{PASTA_ARMAZENAMENTO}/")
        print("   Pressione Ctrl+C para encerrar o servidor")
        print("=" * 60)

        contador_cliente = 1
        while True:
            conn, addr = servidor_sock.accept()
            thread = threading.Thread(
                target=tratar_cliente,
                args=(conn, addr),
                name=f"Thread-Cliente-{contador_cliente}",
                daemon=True
            )
            contador_cliente += 1
            thread.start()

    except KeyboardInterrupt:
        print("\n[*] Encerrando o servidor a pedido do operador...")
    except Exception as e:
        print(f"[ERRO FATAL] Falha no servidor: {e}")
    finally:
        servidor_sock.close()
        print("[*] Servidor finalizado.")


if __name__ == "__main__":
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else PORTA_PADRAO
    iniciar_servidor(porta=porta)
