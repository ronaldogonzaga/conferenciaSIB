"""Leitura e interpretação do arquivo retorno SIB (.RPX — XML ISO-8859-1)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any, BinaryIO

# Sugestões por código de crítica ANS (mensagemSIB / resultadoProcessamento).
ERROR_SUGGESTIONS: dict[str, dict[str, str]] = {
    "0205": {
        "severidade": "alta",
        "titulo": "Nascimento posterior à contratação",
        "sugestao": (
            "Ajuste nascusu para data anterior ou igual a dataini, "
            "ou corrija dataini se a contratação estiver errada."
        ),
        "acao_cadusu": "Revisar nascusu e/ou dataini; reenviar 2-ALTERACAO ou 1-INCLUSAO.",
    },
    "0206": {
        "severidade": "critica",
        "titulo": "Nascimento bloqueado pela Receita Federal",
        "sugestao": (
            "A ANS não aceita retificação de nascimento quando o CPF está "
            "identificado na Receita. Confirme o CPF/nome; se o nascimento "
            "local estiver errado, trate fora do SIB (atendimento ANS)."
        ),
        "acao_cadusu": "Não reenviar alteração de nascusu; alinhar cadastro com a Receita.",
    },
    "0410": {
        "severidade": "critica",
        "titulo": "Já existe ativo com mesmo CPF/plano/contratante",
        "sugestao": (
            "Localize o CCO ativo na confsib com o mesmo CPF + plano + empresa. "
            "Vincule o codcco existente e use posans=4-ATUALIZADO (não reenviar inclusão)."
        ),
        "acao_cadusu": "Copiar CODCCO da confsib e posans=4-ATUALIZADO (ou cancelar duplicidade).",
    },
    "1205": {
        "severidade": "alta",
        "titulo": "Data de contratação fora da competência",
        "sugestao": (
            "Ajuste dataini para no máximo o último dia do mês de competência "
            "do arquivo enviado à ANS."
        ),
        "acao_cadusu": "Corrigir dataini e reenviar o movimento (1-INCLUSAO / 2-ALTERACAO).",
    },
    "1602": {
        "severidade": "alta",
        "titulo": "Documento da empresa contratante ausente",
        "sugestao": (
            "Para plano coletivo, preencha CNPJ, CEI ou CAEPF da empresa contratante "
            "no cadastro enviado ao SIB."
        ),
        "acao_cadusu": "Completar dados do contratante e reenviar inclusão/alteração.",
    },
    "1702": {
        "severidade": "alta",
        "titulo": "Documento da empresa contratante ausente",
        "sugestao": (
            "Preencha CNPJ, CEI ou CAEPF da empresa contratante "
            "(obrigatório em plano coletivo)."
        ),
        "acao_cadusu": "Completar dados do contratante e reenviar.",
    },
    "1802": {
        "severidade": "alta",
        "titulo": "Código do titular não pertence à operadora",
        "sugestao": (
            "Revise o vínculo do dependente (codtit / identificação do titular). "
            "O titular informado não é reconhecido para esta operadora na ANS."
        ),
        "acao_cadusu": "Corrigir identificação do titular e reenviar.",
    },
    "1803": {
        "severidade": "alta",
        "titulo": "Código informado não é de um titular",
        "sugestao": (
            "O código de identificação aponta para um não-titular. "
            "Ajuste parentesco/codtit para o titular correto do contrato."
        ),
        "acao_cadusu": "Corrigir titular do dependente e reenviar.",
    },
    "3005": {
        "severidade": "media",
        "titulo": "CCO já inativo na ANS",
        "sugestao": (
            "Não reenviar 3-EXCLUSAO/CANCELAMENTO: o CCO já está inativo. "
            "Marque posans=4-ATUALIZADO na cadusu."
        ),
        "acao_cadusu": "posans = 4-ATUALIZADO (regra exclusao_cco_ja_inativo_confsib).",
        "fixable": True,
        "fix_label": "Aplicar: posans = 4-ATUALIZADO",
        "fix_action": "posans_atualizado",
    },
    "3011": {
        "severidade": "baixa",
        "titulo": "Dados idênticos aos já cadastrados",
        "sugestao": (
            "O movimento não altera nada na ANS. Concilie localmente com "
            "posans=4-ATUALIZADO para não reenviar a mesma retificação."
        ),
        "acao_cadusu": "posans = 4-ATUALIZADO.",
        "fixable": True,
        "fix_label": "Aplicar: posans = 4-ATUALIZADO",
        "fix_action": "posans_atualizado",
    },
    "3103": {
        "severidade": "alta",
        "titulo": "Data de cancelamento fora da competência",
        "sugestao": (
            "Ajuste datafim (data de cancelamento) para no máximo o último dia "
            "do mês de competência de referência do envio."
        ),
        "acao_cadusu": "Corrigir datafim e reenviar 3-EXCLUSAO.",
    },
    "3205": {
        "severidade": "critica",
        "titulo": "Motivo de cancelamento impede reativação",
        "sugestao": (
            "O motivo de cancelamento existente na ANS não permite reativação "
            "(ex.: código 48). Limpe o CCO antigo e envie como nova inclusão "
            "(posans = 1-INCLUSAO), em vez de 8-REINCLUSAO/REATIVAÇÃO."
        ),
        "acao_cadusu": "codcco = NULL e posans = 1-INCLUSAO.",
        "fixable": True,
        "fix_label": "Aplicar: inclusão (1-INCLUSAO)",
        "fix_action": "posans_inclusao",
    },
    "4202": {
        "severidade": "alta",
        "titulo": "Documento da empresa contratante ausente",
        "sugestao": (
            "Preencha CNPJ, CEI ou CAEPF da empresa contratante no movimento "
            "de mudança contratual / coletivo."
        ),
        "acao_cadusu": "Completar dados do contratante e reenviar.",
    },
}


def suggest_for_error(codigo: str) -> dict[str, Any]:
    code = (codigo or "").strip()
    meta = ERROR_SUGGESTIONS.get(code)
    if meta:
        out = {"codigo_erro": code, **meta}
        out["fixable"] = bool(meta.get("fixable"))
        out["fix_label"] = meta.get("fix_label") or ""
        out["fix_action"] = meta.get("fix_action") or ""
        return out
    return {
        "codigo_erro": code,
        "severidade": "media",
        "titulo": "Crítica ANS sem plano local mapeado",
        "sugestao": (
            "Consulte o manual SIB da ANS para o código e ajuste o campo "
            "indicado no registro rejeitado antes de reenviar."
        ),
        "acao_cadusu": "Revisar manualmente o campo criticado e o POSANS.",
        "fixable": False,
        "fix_label": "",
        "fix_action": "",
    }


def _text(el: ET.Element | None, default: str = "") -> str:
    if el is None or el.text is None:
        return default
    return el.text.strip()


def _findtext(parent: ET.Element, path: str, default: str = "") -> str:
    return _text(parent.find(path), default)


def _read_xml_bytes(data: bytes) -> ET.Element:
    # RPX padrão: encoding ISO-8859-1 (latin-1); aceita UTF-8 como fallback.
    for encoding in ("latin-1", "utf-8", "cp1252"):
        try:
            text = data.decode(encoding)
            return ET.fromstring(text)
        except (UnicodeDecodeError, ET.ParseError):
            continue
    raise ValueError("Não foi possível interpretar o XML do arquivo .RPX")


def _parse_campo_erro(ce: ET.Element) -> dict[str, Any]:
    erros: list[dict[str, Any]] = []
    for er in ce.findall("erro"):
        codigo = _findtext(er, "codigoErro")
        mensagem = _findtext(er, "mensagemErro")
        sug = suggest_for_error(codigo)
        erros.append(
            {
                "codigo_erro": codigo,
                "mensagem_erro": mensagem,
                "severidade": sug["severidade"],
                "titulo": sug["titulo"],
                "sugestao": sug["sugestao"],
                "acao_cadusu": sug["acao_cadusu"],
                "fixable": bool(sug.get("fixable")),
                "fix_label": sug.get("fix_label") or "",
                "fix_action": sug.get("fix_action") or "",
            }
        )
    return {
        "codigo_campo": _findtext(ce, "codigoCampo"),
        "descricao_campo": _findtext(ce, "descricaoCampo"),
        "valor_campo": _findtext(ce, "valorCampo"),
        "erros": erros,
    }


def _parse_registro_rejeitado(reg: ET.Element) -> dict[str, Any]:
    campos = [_parse_campo_erro(ce) for ce in reg.findall("campoErro")]
    erros_flat: list[dict[str, Any]] = []
    for campo in campos:
        for er in campo["erros"]:
            erros_flat.append(
                {
                    **er,
                    "codigo_campo": campo["codigo_campo"],
                    "descricao_campo": campo["descricao_campo"],
                    "valor_campo": campo["valor_campo"],
                }
            )
    principal = erros_flat[0] if erros_flat else {}
    return {
        "cco": (reg.get("cco") or "").strip(),
        "codigo_beneficiario": (reg.get("codigoBeneficiario") or "").strip(),
        "codigo_tipo_movimento": (reg.get("codigoTipoMovimento") or "").strip(),
        "tipo_movimento": (reg.get("tipoMovimento") or "").strip(),
        "campos_erro": campos,
        "erros": erros_flat,
        "codigo_erro": principal.get("codigo_erro", ""),
        "mensagem_erro": principal.get("mensagem_erro", ""),
        "descricao_campo": principal.get("descricao_campo", ""),
        "valor_campo": principal.get("valor_campo", ""),
        "severidade": principal.get("severidade", "media"),
        "sugestao": principal.get("sugestao", ""),
        "acao_cadusu": principal.get("acao_cadusu", ""),
        "titulo_critica": principal.get("titulo", ""),
    }


def _parse_registro_incluido(reg: ET.Element) -> dict[str, Any]:
    return {
        "codigo_beneficiario": (reg.get("codigoBeneficiario") or "").strip(),
        "cco": _findtext(reg, "cco"),
        "nome_beneficiario": _findtext(reg, "nomeBeneficiario"),
    }


def _parse_consolidado(cons: ET.Element | None) -> dict[str, Any]:
    if cons is None:
        return {"erros": [], "movimentos": [], "total": {}}

    erros = []
    for er in cons.findall("consolidadoErroProcessamento/erro"):
        codigo = _findtext(er, "codigoErro")
        sug = suggest_for_error(codigo)
        erros.append(
            {
                "codigo_erro": codigo,
                "mensagem_erro": _findtext(er, "mensagemErro"),
                "quantidade": int(_findtext(er, "quantidadeOcorrenciaErro") or "0"),
                "severidade": sug["severidade"],
                "titulo": sug["titulo"],
                "sugestao": sug["sugestao"],
                "acao_cadusu": sug["acao_cadusu"],
                "fixable": bool(sug.get("fixable")),
                "fix_label": sug.get("fix_label") or "",
                "fix_action": sug.get("fix_action") or "",
            }
        )
    erros.sort(key=lambda x: (-x["quantidade"], x["codigo_erro"]))

    movimentos = []
    cp = cons.find("consolidadoProcessamento")
    if cp is not None:
        for child in cp:
            movimentos.append(
                {
                    "tipo": child.tag.replace("consolidado", ""),
                    "quantidade_registros": int(
                        _findtext(child, "quantidadeRegistros") or "0"
                    ),
                    "quantidade_processados": int(
                        _findtext(child, "quantidadeProcessados") or "0"
                    ),
                    "quantidade_rejeitados": int(
                        _findtext(child, "quantidadeRejeitados") or "0"
                    ),
                    "percentual_acerto": float(
                        _findtext(child, "percentualAcerto") or "0"
                    ),
                }
            )

    total = next((m for m in movimentos if m["tipo"] == "Total"), {})
    return {"erros": erros, "movimentos": movimentos, "total": total}


def parse_rpx_bytes(data: bytes, *, source_name: str = "") -> dict[str, Any]:
    root = _read_xml_bytes(data)
    if root.tag != "mensagemSIB":
        raise ValueError(
            f"Raiz XML inesperada '{root.tag}'. Esperado mensagemSIB (retorno SIB)."
        )

    cab = root.find("cabecalho") or ET.Element("cabecalho")
    ident = cab.find("identificacaoTransacao")
    tipo = _findtext(ident, "tipoTransacao") if ident is not None else ""
    if tipo and "RESULTADO" not in tipo.upper():
        raise ValueError(
            f"tipoTransacao='{tipo}'. Esperado RESULTADO DO PROCESSAMENTO (.RPX)."
        )

    ap = root.find(".//arquivoProcessado")
    if ap is None:
        raise ValueError("XML sem arquivoProcessado / resultadoProcessamento.")

    protocolo = {
        "numero_protocolo": _findtext(ap, "protocoloProcessamento/numeroProtocolo"),
        "nome_arquivo": _findtext(ap, "protocoloProcessamento/nomeArquivo"),
    }

    rejeitados = [
        _parse_registro_rejeitado(r)
        for r in ap.findall("registrosRejeitados/registroRejeitado")
    ]
    incluidos = [
        _parse_registro_incluido(r)
        for r in ap.findall("registrosIncluidos/registroIncluido")
    ]
    consolidado = _parse_consolidado(ap.find("consolidado"))

    por_erro = Counter(r["codigo_erro"] for r in rejeitados if r["codigo_erro"])
    por_movimento = Counter(
        r["tipo_movimento"] or r["codigo_tipo_movimento"] for r in rejeitados
    )
    por_severidade = Counter(r["severidade"] for r in rejeitados)

    header = {
        "tipo_transacao": tipo,
        "sequencial": _findtext(ident, "sequencialTransacao") if ident is not None else "",
        "data_hora": (
            _findtext(ident, "dataHoraRegistroTransacao") if ident is not None else ""
        ),
        "cnpj_origem": _findtext(cab, "origem/cnpj"),
        "registro_ans": _findtext(cab, "destino/registroANS"),
        "versao_padrao": _findtext(cab, "versaoPadrao"),
        "hash": _findtext(root, "epilogo/hash"),
    }

    return {
        "source_name": source_name,
        "header": header,
        "protocolo": protocolo,
        "resumo": {
            "total_rejeitados": len(rejeitados),
            "total_incluidos": len(incluidos),
            "por_codigo_erro": [
                {
                    "codigo_erro": code,
                    "quantidade": qtd,
                    **{k: v for k, v in suggest_for_error(code).items() if k != "codigo_erro"},
                }
                for code, qtd in por_erro.most_common()
            ],
            "por_movimento": [
                {"tipo_movimento": mov, "quantidade": qtd}
                for mov, qtd in por_movimento.most_common()
            ],
            "por_severidade": dict(por_severidade),
        },
        "consolidado": consolidado,
        "rejeitados": rejeitados,
        "incluidos": incluidos,
    }


def _normalize_path(path: str | Path) -> Path:
    raw = str(path).strip().strip('"').strip("'")
    # Aceita UNC com barras normais: //servidor/c$/pasta/arquivo.RPX
    if raw.startswith("//") and not raw.startswith("\\\\"):
        raw = "\\\\" + raw[2:].replace("/", "\\")
    return Path(raw)


def parse_rpx(
    path: str | Path | None = None,
    *,
    fileobj: BinaryIO | None = None,
    source_name: str = "",
) -> dict[str, Any]:
    """Parseia .RPX a partir de caminho UNC/local ou stream de upload."""
    if fileobj is not None:
        data = fileobj.read()
        name = source_name or getattr(fileobj, "filename", "") or "upload.RPX"
        return parse_rpx_bytes(data, source_name=str(name))

    if not path:
        raise ValueError("Informe o caminho do arquivo .RPX ou envie o upload.")

    p = _normalize_path(path)
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {p}")
    if p.suffix.upper() not in {".RPX", ".XML"}:
        raise ValueError("Extensão esperada: .RPX (retorno SIB) ou .XML.")

    return parse_rpx_bytes(p.read_bytes(), source_name=str(p))
