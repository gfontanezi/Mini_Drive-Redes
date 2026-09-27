# -*- coding: utf-8 -*-
"""
cliente.py - Cliente CLI para a Mini Nuvem Pessoal.
Disciplina: Redes de Computadores
Protocolo: NSP (Nuvem Storage Protocol)
"""

import os
import sys
import socket
from protocolo import enviar_msg, receber_msg, enviar_arquivo, receber_arquivo

HOST_PADRAO = "127.0.0.1"
PORTA_PADRAO = 5000
PASTA_DOWNLOADS = "downloads"


def formatar_tamanho(tamanho_bytes):
    """
    Converte bytes para formato legivel (B, KB, MB, GB).
    """
    for unidade in ["B", "KB", "MB", "GB"]:
        if tamanho_bytes < 1024.0:
            return f"{tamanho_bytes:.1f} {unidade}" if unidade != "B" else f"{tamanho_bytes} B"
        tamanho_bytes /= 1024.0
    return f"{tamanho_bytes:.1f} TB"


def conectar_servidor(host, porta):
    """
    Cria o socket TCP e conecta ao servidor.
    """
    print(f"[*] Conectando ao servidor em {host}:{porta}...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, porta))
        print("[+] Conexao TCP estabelecida com sucesso!")
        return sock
    except Exception as e:
        print(f"[ERRO] Nao foi possivel conectar ao servidor: {e}")
        return None


def realizar_login(sock):
    """
    Solicita o nome de usuario e envia a mensagem CONNECT.
    """
    while True:
        try:
            usuario = input("Digite seu nome de usuario para login: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n[*] Operacao cancelada.")
            return None

        if not usuario:
            print("[!] O nome de usuario nao pode ser vazio. Tente novamente.")
            continue
        if "|" in usuario:
            print("[!] O nome de usuario nao pode conter o caractere '|'. Tente novamente.")
            continue
        break

    enviar_msg(sock, "CONNECT", usuario)
    resposta = receber_msg(sock)

    if not resposta:
        print("[ERRO] O servidor encerrou a conexao durante o login.")
        return None

    comando = resposta[0]
    status = resposta[1] if len(resposta) > 1 else ""
    mensagem = resposta[2] if len(resposta) > 2 else ""

    if comando == "WELCOME" and status == "OK":
        print(f"[+] Login aceito! Mensagem do servidor: {mensagem}")
        return usuario
    else:
        print(f"[ERRO] Falha na autenticacao: {mensagem}")
        return None


def executar_upload(sock):
    """
    Solicita o caminho de um arquivo local e realiza o upload para o servidor.
    """
    try:
        caminho_bruto = input("Digite o caminho do arquivo para enviar: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n[*] Upload cancelado.")
        return

    caminho = caminho_bruto.strip("\"'")
    if not caminho:
        print("[!] Caminho nao informado.")
        return

    if not os.path.isfile(caminho):
        print(f"[!] Arquivo '{caminho}' nao encontrado no disco local.")
        return

    nome_arquivo = os.path.basename(caminho)
    if "|" in nome_arquivo:
        print("[!] O nome do arquivo nao pode conter o caractere '|'.")
        return

    tamanho_bytes = os.path.getsize(caminho)
    print(f"[*] Solicitando upload de '{nome_arquivo}' ({formatar_tamanho(tamanho_bytes)})...")

    enviar_msg(sock, "UPLOAD_REQ", nome_arquivo, tamanho_bytes)
    resposta = receber_msg(sock)

    if not resposta:
        print("[ERRO] Conexao com o servidor perdida durante solicitacao de upload.")
        return

    if resposta[0] == "STATUS" and len(resposta) > 1 and resposta[1] == "OK":
        print(f"[+] Servidor autorizou. Transmitindo {formatar_tamanho(tamanho_bytes)}...")

        def mostrar_progresso(enviados, total):
            if total > 0:
                pct = (enviados / total) * 100
                print(f"\r  -> Enviando: {formatar_tamanho(enviados)} / {formatar_tamanho(total)} ({pct:.1f}%)", end="", flush=True)
            else:
                print(f"\r  -> Enviando arquivo vazio (0 bytes)...", end="", flush=True)

        try:
            enviar_arquivo(sock, caminho, callback_progresso=mostrar_progresso)
            print("\n[+] Upload finalizado com sucesso!")
        except Exception as e:
            print(f"\n[ERRO] Falha na transmissao do arquivo: {e}")
    else:
        motivo = resposta[2] if len(resposta) > 2 else "Recusado pelo servidor"
        print(f"[ERRO] Servidor recusou upload: {motivo}")


def executar_listagem(sock):
    """
    Envia LIST_REQ e exibe a tabela de arquivos remotos salvos na nuvem.
    """
    print("[*] Consultando arquivos na nuvem...")
    enviar_msg(sock, "LIST_REQ")
    resposta = receber_msg(sock)

    if not resposta or resposta[0] != "LIST_RESP":
        print("[ERRO] Falha ao obter lista de arquivos do servidor.")
        return []

    try:
        total = int(resposta[1])
    except (ValueError, IndexError):
        total = 0

    dados = resposta[2] if len(resposta) > 2 else ""

    print("\n" + "-" * 55)
    print(f"{'NOME DO ARQUIVO':<35} | {'TAMANHO':<15}")
    print("-" * 55)

    if total == 0 or not dados:
        print("   (Nenhum arquivo armazenado na sua nuvem ainda)")
        print("-" * 55)
        return []

    itens = [item for item in dados.split(";") if item.strip()]
    nomes_arquivos = []

    for item in itens:
        partes = item.split(":")
        nome = partes[0]
        tam = int(partes[1]) if len(partes) > 1 and partes[1].isdigit() else 0
        nomes_arquivos.append(nome)
        print(f"{nome:<35} | {formatar_tamanho(tam):<15}")

    print("-" * 55)
    print(f"Total: {len(nomes_arquivos)} arquivo(s) armazenado(s).\n")
    return nomes_arquivos


def executar_download(sock):
    """
    Solicita o download de um arquivo remoto e grava na pasta local 'downloads/'.
    """
    try:
        nome_arquivo = input("Digite o nome do arquivo que deseja baixar: ").strip().strip("\"'")
    except (KeyboardInterrupt, EOFError):
        print("\n[*] Download cancelado.")
        return

    if not nome_arquivo:
        print("[!] Nome do arquivo nao pode ser vazio.")
        return

    print(f"[*] Solicitando download de '{nome_arquivo}'...")
    enviar_msg(sock, "DOWNLOAD_REQ", nome_arquivo)
    resposta = receber_msg(sock)

    if not resposta:
        print("[ERRO] Conexao perdida ao solicitar download.")
        return

    if resposta[0] == "STATUS" and len(resposta) > 1 and resposta[1] == "OK":
        try:
            tamanho_bytes = int(resposta[2])
        except (ValueError, IndexError):
            tamanho_bytes = 0

        print(f"[+] Arquivo encontrado no servidor! Tamanho: {formatar_tamanho(tamanho_bytes)}.")
        os.makedirs(PASTA_DOWNLOADS, exist_ok=True)
        caminho_destino = os.path.join(PASTA_DOWNLOADS, nome_arquivo)

        def mostrar_progresso(recebidos, total):
            if total > 0:
                pct = (recebidos / total) * 100
                print(f"\r  -> Baixando: {formatar_tamanho(recebidos)} / {formatar_tamanho(total)} ({pct:.1f}%)", end="", flush=True)
            else:
                print(f"\r  -> Baixando arquivo vazio (0 bytes)...", end="", flush=True)

        sucesso = receber_arquivo(sock, tamanho_bytes, caminho_destino, callback_progresso=mostrar_progresso)
        if sucesso:
            print(f"\n[+] Download concluido com sucesso! Salvo em: {caminho_destino}")
        else:
            print(f"\n[ERRO] Queda de conexao durante recepcao de '{nome_arquivo}'.")
    else:
        motivo = resposta[2] if len(resposta) > 2 else "Arquivo nao encontrado"
        print(f"[ERRO] Nao foi possivel baixar o arquivo: {motivo}")


def menu_interativo(sock, usuario):
    """
    Menu interativo completo do cliente da Nuvem Pessoal.
    """
    while True:
        print("\n" + "=" * 45)
        print(f"   MINI NUVEM PESSOAL - [{usuario}]")
        print("=" * 45)
        print("1. Enviar arquivo (Upload)")
        print("2. Listar meus arquivos (List)")
        print("3. Baixar arquivo (Download)")
        print("4. Sair (Desconectar)")
        print("=" * 45)

        try:
            opcao = input("Escolha uma opcao: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n[*] Interrupcao detectada. Encerrando...")
            opcao = "4"

        if opcao == "1":
            executar_upload(sock)
        elif opcao == "2":
            executar_listagem(sock)
        elif opcao == "3":
            executar_download(sock)
        elif opcao == "4" or opcao.lower() in ("sair", "exit", "quit"):
            print("[*] Solicitando encerramento gracioso (DISCONNECT)...")
            enviar_msg(sock, "DISCONNECT")
            resposta = receber_msg(sock)
            if resposta and resposta[0] == "STATUS":
                msg_servidor = resposta[2] if len(resposta) > 2 else ""
                print(f"[+] Servidor confirmou: {msg_servidor}")
            print("[*] Sessao finalizada com sucesso. Ate logo!")
            break
        else:
            print("[!] Opcao invalida. Digite 1, 2, 3 ou 4.")


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else HOST_PADRAO
    porta = int(sys.argv[2]) if len(sys.argv) > 2 else PORTA_PADRAO

    sock = conectar_servidor(host, porta)
    if not sock:
        return

    try:
        usuario = realizar_login(sock)
        if usuario:
            menu_interativo(sock, usuario)
    finally:
        sock.close()


if __name__ == "__main__":
    main()
