# -*- coding: utf-8 -*-
"""
test_casos_limite.py - Casos limite do protocolo NSP.

Sobe o proprio servidor numa thread (porta 5066), com o prazo do keep-alive
reduzido para 3 segundos. Basta executar:

    python test_casos_limite.py

Cada caso mostra OK quando o servidor se comportou como o protocolo define.
Os casos marcados como ERRO CONHECIDO mostram problemas que ja sabemos que
existem (estao descritos no relatorio, secao 11).
"""

import os
import time
import socket
import hashlib
import threading

import servidor
from protocolo import enviar_msg, receber_msg, enviar_arquivo, receber_arquivo

HOST = "127.0.0.1"
PORTA = 5066
servidor.TIMEOUT_KEEPALIVE = 3

resultados = []


def registrar(codigo, descricao, passou, detalhe, conhecido=False):
    if passou:
        situacao = "OK"
    elif conhecido:
        situacao = "ERRO CONHECIDO"
    else:
        situacao = "FALHOU"
    resultados.append((codigo, situacao))
    print(f"[{situacao}] {codigo} {descricao}")
    print(f"      {detalhe}")


def conectar(usuario=None):
    s = socket.create_connection((HOST, PORTA))
    s.settimeout(20)
    if usuario is not None:
        enviar_msg(s, "CONNECT", usuario)
        receber_msg(s)
    return s


def upload(s, nome, dados):
    enviar_msg(s, "UPLOAD_REQ", nome, len(dados))
    resp = receber_msg(s)
    if resp[1] != "OK":
        return resp
    s.sendall(dados)
    return receber_msg(s)


def md5(dados):
    return hashlib.md5(dados).hexdigest()


def caminho(usuario, nome):
    return os.path.join(servidor.PASTA_ARMAZENAMENTO, usuario, nome)


def e1():
    s = conectar("e1")
    enviar_msg(s, "CONNECT", "outro")
    r1 = receber_msg(s)
    enviar_msg(s, "LIST_REQ")
    r2 = receber_msg(s)
    s.close()
    registrar("E1", "CONNECT depois de ja autenticado",
              r1 == ["STATUS", "ERRO", "Comando desconhecido 'CONNECT'"] and r2[0] == "LIST_RESP",
              f"resposta: {'|'.join(r1)}; a sessao continua (LIST_REQ respondido)")


def e2():
    s = conectar()
    enviar_msg(s, "CONNECT", "")
    r1 = receber_msg(s)
    r2 = receber_msg(s)
    s.close()
    registrar("E2", "CONNECT com nome vazio",
              r1 == ["WELCOME", "ERRO", "Nome de usuario invalido ou vazio"] and r2 is None,
              f"resposta: {'|'.join(r1)}; conexao fechada pelo servidor")


def e3():
    s = conectar("e3")
    casos = [("a.txt",), ("a.txt", "-5"), ("a.txt", "abc"), ("", "3")]
    respostas = []
    for campos in casos:
        enviar_msg(s, "UPLOAD_REQ", *campos)
        respostas.append(receber_msg(s))
    enviar_msg(s, "LIST_REQ")
    continua = receber_msg(s)[0] == "LIST_RESP"
    s.close()
    todos_erro = all(r[0] == "STATUS" and r[1] == "ERRO" for r in respostas)
    registrar("E3", "UPLOAD_REQ sem tamanho, tamanho negativo, tamanho texto, nome vazio",
              todos_erro and continua,
              "respostas: " + " / ".join(r[2] for r in respostas) + "; a sessao continua")


def e5():
    s = conectar("e5")
    r = upload(s, "../../hack.txt", b"x")
    s.close()
    dentro = os.path.exists(caminho("e5", "hack.txt"))
    registrar("E5", "UPLOAD_REQ com caminho no nome (../../hack.txt)",
              r == ["STATUS", "OK", "recebido"] and dentro,
              f"arquivo gravado dentro da pasta do usuario: {dentro}")


def e6():
    s = conectar("e6")
    upload(s, "a;b.txt", b"12")
    upload(s, "c:d.txt", b"123")
    enviar_msg(s, "LIST_REQ")
    r = receber_msg(s)
    s.close()
    itens = r[2].split(";")
    registrar("E6", "Nomes de arquivo com ; e :",
              len(itens) == 2,
              f"LIST_RESP recebido: {'|'.join(r)} (o cliente separa em {len(itens)} itens em vez de 2)",
              conhecido=True)


def e7():
    s = conectar("../fora_e7")
    s.close()
    fora = os.path.isdir("fora_e7")
    registrar("E7", "Nome de usuario com ../",
              not fora,
              f"pasta criada fora de armazenamento/: {fora}",
              conhecido=True)


def e8():
    s = conectar("joão")
    r = upload(s, "relatório ação.txt", "ç".encode())
    enviar_msg(s, "LIST_REQ")
    lista = receber_msg(s)
    s.close()
    registrar("E8", "Usuario e arquivo com acentos",
              r == ["STATUS", "OK", "recebido"] and "relatório ação.txt" in lista[2],
              f"LIST_RESP: {'|'.join(lista)}")


def e9():
    s = conectar("e9")
    enviar_msg(s, "UPLOAD_REQ", "parcial.bin", 1000)
    receber_msg(s)
    s.sendall(b"0123456789")
    inicio = time.time()
    r = receber_msg(s)
    espera = time.time() - inicio
    s.close()
    time.sleep(0.2)
    sobrou = os.path.exists(caminho("e9", "parcial.bin"))
    registrar("E9", "Upload anuncia 1000 bytes, envia 10 e para",
              r is None and not sobrou and 2.8 <= espera <= 4,
              f"servidor fechou a conexao apos {espera:.2f}s (prazo de teste: 3s); arquivo parcial apagado: {not sobrou}")


def e10():
    a = os.urandom(3000000)
    b = os.urandom(3000000)

    def enviar(dados):
        s = conectar("e10")
        upload(s, "mesmo.bin", dados)
        s.close()

    t1 = threading.Thread(target=enviar, args=(a,))
    t2 = threading.Thread(target=enviar, args=(b,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    with open(caminho("e10", "mesmo.bin"), "rb") as f:
        final = f.read()
    igual = md5(final) in (md5(a), md5(b))
    registrar("E10", "Dois clientes do mesmo usuario enviam o mesmo nome ao mesmo tempo",
              igual,
              f"arquivo final igual a um dos dois enviados: {igual}",
              conhecido=True)


def e11():
    s = conectar("e11")
    enviar_msg(s, "DOWNLOAD_REQ", "")
    r1 = receber_msg(s)
    enviar_msg(s, "PING")
    r2 = receber_msg(s)
    s.sendall(b"\n")
    enviar_msg(s, "LIST_REQ")
    r3 = receber_msg(s)
    enviar_msg(s, "XYZ")
    r4 = receber_msg(s)
    enviar_msg(s, "list_req")
    r5 = receber_msg(s)
    s.close()
    registrar("E11", "DOWNLOAD_REQ sem nome",
              r1 == ["STATUS", "ERRO", "Nome do arquivo nao especificado"], f"resposta: {'|'.join(r1)}")
    registrar("E12", "PING sem numero de sequencia",
              r2 == ["PONG", ""], f"resposta: {'|'.join(r2)}")
    registrar("E13", "Linha vazia antes de um comando",
              r3[0] == "LIST_RESP", "a linha vazia foi ignorada e o LIST_REQ seguinte foi respondido")
    registrar("E16", "Comando desconhecido (XYZ) e comando em minusculas (list_req)",
              r4[1] == "ERRO" and r5[1] == "ERRO", f"respostas: {r4[2]} / {r5[2]}")


def e14():
    dados = os.urandom(100 * 1024 * 1024)
    with open("temp_100mb.bin", "wb") as f:
        f.write(dados)
    s = conectar("e14")
    inicio = time.time()
    enviar_msg(s, "UPLOAD_REQ", "grande.bin", len(dados))
    receber_msg(s)
    enviar_arquivo(s, "temp_100mb.bin")
    r = receber_msg(s)
    t_up = time.time() - inicio
    inicio = time.time()
    enviar_msg(s, "DOWNLOAD_REQ", "grande.bin")
    tam = int(receber_msg(s)[2])
    receber_arquivo(s, tam, "temp_100mb_volta.bin")
    t_down = time.time() - inicio
    s.close()
    with open("temp_100mb_volta.bin", "rb") as f:
        igual = md5(f.read()) == md5(dados)
    os.remove("temp_100mb.bin")
    os.remove("temp_100mb_volta.bin")
    registrar("E14", "Arquivo de 100 MB (upload e download)",
              r == ["STATUS", "OK", "recebido"] and igual,
              f"upload {t_up:.2f}s, download {t_down:.2f}s, MD5 igual: {igual}")


def e15():
    certos = []

    def cliente(i):
        s = conectar(f"multi{i}")
        dados = os.urandom(1024 * 1024)
        r = upload(s, "m.bin", dados)
        s.close()
        with open(caminho(f"multi{i}", "m.bin"), "rb") as f:
            certos.append(r == ["STATUS", "OK", "recebido"] and md5(f.read()) == md5(dados))

    threads = [threading.Thread(target=cliente, args=(i,)) for i in range(10)]
    inicio = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    registrar("E15", "10 clientes enviando 1 MB cada ao mesmo tempo",
              sum(certos) == 10,
              f"{sum(certos)} de 10 arquivos corretos em {time.time() - inicio:.2f}s")


def e20():
    s = conectar("e20")
    upload(s, "x.txt", b"primeiro")
    upload(s, "x.txt", b"segundo")
    s.close()
    with open(caminho("e20", "x.txt"), "rb") as f:
        conteudo = f.read()
    registrar("E20", "Upload de um nome que ja existe",
              conteudo == b"segundo",
              f"conteudo final: {conteudo!r} (o arquivo antigo foi substituido)")


if __name__ == "__main__":
    print("=" * 60)
    print("   CASOS LIMITE DO PROTOCOLO NSP")
    print("=" * 60)
    servidor.print = lambda *a, **k: None   # esconde o log do servidor nesta bateria
    threading.Thread(target=servidor.iniciar_servidor, kwargs={"host": HOST, "porta": PORTA}, daemon=True).start()
    time.sleep(0.5)
    for caso in (e1, e2, e3, e5, e6, e7, e8, e9, e10, e11, e14, e15, e20):
        caso()
    ok = sum(1 for _, s in resultados if s == "OK")
    conhecidos = sum(1 for _, s in resultados if s == "ERRO CONHECIDO")
    falhas = sum(1 for _, s in resultados if s == "FALHOU")
    print("=" * 60)
    print(f"   {ok} OK, {conhecidos} erros conhecidos, {falhas} falhas")
    print("=" * 60)
