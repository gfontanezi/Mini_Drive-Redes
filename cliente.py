import os
import sys
import time
import socket
import threading
from protocolo import (enviar_msg, receber_msg, enviar_arquivo, receber_arquivo, INTERVALO_KEEPALIVE, TIMEOUT_KEEPALIVE)

HOST_PADRAO = "127.0.0.1"
PORTA_PADRAO = 5000
PASTA_DOWNLOADS = "downloads"


class Sessao:
    # Guarda o socket da sessao e roda a thread de keep-alive.

    def __init__(self, sock):
        self.sock = sock
        self.trava = threading.Lock()
        self.ativa = True
        self.seq = 0
        self.ultimo_rtt_ms = None  # tempo PING -> PONG da ultima vez

    def iniciar_keepalive(self):
        threading.Thread(target=self.enviar_pings, daemon=True).start()

    def enviar_pings(self):
        while self.ativa:
            time.sleep(INTERVALO_KEEPALIVE)
            with self.trava:
                if not self.ativa:
                    break
                self.seq += 1
                try:
                    inicio = time.time()
                    enviar_msg(self.sock, "PING", self.seq)
                    resposta = receber_msg(self.sock)
                except OSError:
                    resposta = None

            if resposta and resposta[0] == "PONG" and resposta[1] == str(self.seq):
                self.ultimo_rtt_ms = (time.time() - inicio) * 1000
            else:
                self.ativa = False
                print("\n[KEEPALIVE] O servidor nao respondeu ao PING. Conexao perdida.")
                print("[KEEPALIVE] Pressione Enter para sair.", flush=True)


def formatar_tamanho(tamanho_bytes):

    # Converte bytes para formato legivel (B, KB, MB, GB).
    
    for unidade in ["B", "KB", "MB", "GB"]:
        if tamanho_bytes < 1024.0:
            if unidade != "B":
                return f"{tamanho_bytes:.1f} {unidade}"
            else:
                return f"{tamanho_bytes} B"
        tamanho_bytes /= 1024.0
    return f"{tamanho_bytes:.1f} TB"


def conectar_servidor(host, porta):
    
    # Cria o socket TCP e conecta ao servidor.
    
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
 
    # Solicita o nome de usuario e envia a mensagem CONNECT.

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
    if len(resposta) > 1:
        status = resposta[1]
    else:
        status = ""
    if len(resposta) > 2:
        mensagem = resposta[2]
    else:
        mensagem = ""

    if comando == "WELCOME" and status == "OK":
        print(f"[+] Login aceito! Mensagem do servidor: {mensagem}")
        return usuario
    else:
        print(f"[ERRO] Falha na autenticacao: {mensagem}")
        return None


def executar_upload(sessao):

    # Solicita o caminho de um arquivo local e realiza o upload para o servidor.

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

    with sessao.trava:
        executar_upload_rede(sessao.sock, caminho, nome_arquivo, tamanho_bytes)


def executar_upload_rede(sock, caminho, nome_arquivo, tamanho_bytes):
  
    # Parte de rede do upload: UPLOAD_REQ -> STATUS|OK|pronto -> bytes -> STATUS|OK|recebido.
  
   
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
        except Exception as e:
            print(f"\n[ERRO] Falha na transmissao do arquivo: {e}")
            return

        # Espera o servidor confirmar que recebeu todos os bytes
        confirmacao = receber_msg(sock)
        if confirmacao and confirmacao[0] == "STATUS" and confirmacao[1] == "OK":
            print("\n[+] Upload finalizado: servidor confirmou o recebimento!")
            return True
        else:
            print("\n[ERRO] O servidor nao confirmou o recebimento do arquivo.")
    else:
        if len(resposta) > 2:
            motivo = resposta[2]
        else:
            motivo = "Recusado pelo servidor"
        print(f"[ERRO] Servidor recusou upload: {motivo}")


def executar_listagem(sessao):

    # Envia LIST_REQ e exibe a tabela de arquivos remotos salvos na nuvem.

    print("[*] Consultando arquivos na nuvem...")
    with sessao.trava:
        enviar_msg(sessao.sock, "LIST_REQ")
        resposta = receber_msg(sessao.sock)

    if not resposta or resposta[0] != "LIST_RESP":
        print("[ERRO] Falha ao obter lista de arquivos do servidor.")
        return []

    try:
        total = int(resposta[1])
    except (ValueError, IndexError):
        total = 0

    if len(resposta) > 2:
        dados = resposta[2]
    else:
        dados = ""

    print("\n" + "-" * 55)
    print(f"{'NOME DO ARQUIVO':<35} | {'TAMANHO':<15}")
    print("-" * 55)

    if total == 0 or not dados:
        print("(Nenhum arquivo armazenado na sua nuvem ainda)")
        print("-" * 55)
        return []

    itens = []
    for item in dados.split(";"):
        if item.strip():
            itens.append(item)

    nomes_arquivos = []

    for item in itens:
        partes = item.split(":")
        nome = partes[0]
        if len(partes) > 1 and partes[1].isdigit():
            tam = int(partes[1])
        else:
            tam = 0
        nomes_arquivos.append(nome)
        print(f"{nome:<35} | {formatar_tamanho(tam):<15}")

    print("-" * 55)
    print(f"Total: {len(nomes_arquivos)} arquivo(s) armazenado(s).\n")
    return nomes_arquivos


def executar_download(sessao):
    # Solicita o download de um arquivo remoto e grava na pasta local 'downloads/'.

    try:
        nome_arquivo = input("Digite o nome do arquivo que deseja baixar: ").strip().strip("\"'")
    except (KeyboardInterrupt, EOFError):
        print("\n[*] Download cancelado.")
        return

    if not nome_arquivo:
        print("[!] Nome do arquivo nao pode ser vazio.")
        return

    print(f"[*] Solicitando download de '{nome_arquivo}'...")
    with sessao.trava:
        executar_download_rede(sessao.sock, nome_arquivo)


def executar_download_rede(sock, nome_arquivo):
    # Parte de rede do download: DOWNLOAD_REQ -> STATUS|OK|<tam> -> bytes.

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
        if len(resposta) > 2:
            motivo = resposta[2]
        else:
            motivo = "Arquivo nao encontrado"
        print(f"[ERRO] Nao foi possivel baixar o arquivo: {motivo}")


def menu_interativo(sessao, usuario):

    # Menu interativo completo do cliente da Nuvem Pessoal.
 
    while sessao.ativa:
        print("\n" + "=" * 45)
        print(f"MINI NUVEM PESSOAL - [{usuario}]")
        print("=" * 45)
        print("1. Enviar arquivo (Upload)")
        print("2. Listar meus arquivos (List)")
        print("3. Baixar arquivo (Download)")
        print("4. Sair (Desconectar)")
        print("5. Ver keep-alive (ultimo PING)")
        print("=" * 45)

        try:
            opcao = input("Escolha uma opcao: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n[*] Interrupcao detectada. Encerrando...")
            opcao = "4"

        if not sessao.ativa:
            break

        try:
            if opcao == "1":
                executar_upload(sessao)
            elif opcao == "2":
                executar_listagem(sessao)
            elif opcao == "3":
                executar_download(sessao)
            elif opcao == "4" or opcao.lower() in ("sair", "exit", "quit"):
                print("[*] Solicitando encerramento (DISCONNECT)...")
                sessao.ativa = False  # avisa a thread de keep-alive para parar
                with sessao.trava:
                    enviar_msg(sessao.sock, "DISCONNECT")
                    resposta = receber_msg(sessao.sock)
                if resposta and resposta[0] == "STATUS":
                    if len(resposta) > 2:
                        msg_servidor = resposta[2]
                    else:
                        msg_servidor = ""
                    print(f"[+] Servidor confirmou: {msg_servidor}")
                print("[*] Sessao finalizada com sucesso. Ate logo!")
            elif opcao == "5":
                if sessao.ultimo_rtt_ms is not None:
                    rtt = f"{sessao.ultimo_rtt_ms:.2f} ms"
                else:
                    rtt = "(nenhum PING ainda)"
                print(f"[*] PING a cada {INTERVALO_KEEPALIVE}s | PINGs enviados: {sessao.seq} | ultimo RTT: {rtt}")
            else:
                print("[!] Opcao invalida. Digite um numero de 1 a 5.")
        except OSError as e:
            print(f"[ERRO] Conexao com o servidor perdida: {e}")
            sessao.ativa = False


def main():
    if len(sys.argv) > 1:
        host = sys.argv[1]
    else:
        host = HOST_PADRAO
    if len(sys.argv) > 2:
        porta = int(sys.argv[2])
    else:
        porta = PORTA_PADRAO

    sock = conectar_servidor(host, porta)
    if not sock:
        return

    try:
        usuario = realizar_login(sock)
        if usuario:
            # Espera por resposta do servidor tambem tem um prazo
            sock.settimeout(TIMEOUT_KEEPALIVE)
            sessao = Sessao(sock)
            sessao.iniciar_keepalive()
            menu_interativo(sessao, usuario)
    finally:
        sock.close()


if __name__ == "__main__":
    main()
