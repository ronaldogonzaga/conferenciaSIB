from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import Config
from db import execute_returning, fetch_all, fetch_count
from validators.sib_rules import (
    ANS_FLEX_ALGUM_MARCADO_C,
    ATIVO_SIB_CAMPOS_AUSENTES,
    CONFSIB_LATERAL,
    CONFSIB_LATERAL_IDENTIDADE,
    CONFSIB_PODE_PREENCHER_SIB,
    NASC_CONFSIB,
    SIB_FLEX_ALGUM_DIFF,
    SIB_FLEX_FLAG_CASE,
    SIB_FLEX_PREVIEW_FLAGS,
)


@dataclass(frozen=True)
class FixPlan:
    rule_id: str
    label: str
    summary: str
    fields: tuple[str, ...]

    preview_sql: str


    apply_sql: str

    count_sql: str


def _limit() -> str:
    return f" LIMIT {Config.MAX_ROWS}"


_AUDIT = "dataultalt = CURRENT_DATE, dtope = CURRENT_TIMESTAMP"


FIX_PLANS: dict[str, FixPlan] = {
    "inativo_sem_cco_nao_atualizado": FixPlan(
        rule_id="inativo_sem_cco_nao_atualizado",
        label="Ajustar POSANS para 4-ATUALIZADO",
        summary="INATIVO sem CCO não deve ter movimento SIB pendente → posans = 4-ATUALIZADO.",
        fields=("posans",),
        preview_sql=f"""
            SELECT id, codtit, codusu, nomeusu, situusu, codcco,
                   posans AS posans_atual,
                   '4-ATUALIZADO'::varchar AS posans_novo
            FROM cadusu
            WHERE situusu = 'INATIVO'
              AND COALESCE(TRIM(codcco), '') = ''
              AND posans <> '4-ATUALIZADO'
            ORDER BY id
            {_limit()}
        """,
        apply_sql=f"""
            UPDATE cadusu SET
                posans = '4-ATUALIZADO',
                {_AUDIT}
            WHERE id = ANY(%s)
              AND situusu = 'INATIVO'
              AND COALESCE(TRIM(codcco), '') = ''
              AND posans <> '4-ATUALIZADO'
            RETURNING id, codtit, codusu, nomeusu, posans
        """,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE situusu = 'INATIVO'
              AND COALESCE(TRIM(codcco), '') = ''
              AND posans <> '4-ATUALIZADO'
        """,
    ),
    "ativo_com_cco_inclusao": FixPlan(
        rule_id="ativo_com_cco_inclusao",
        label="Ajustar POSANS para 4-ATUALIZADO",
        summary="ATIVO com CCO já incluído na ANS → posans = 4-ATUALIZADO.",
        fields=("posans",),
        preview_sql=f"""
            SELECT id, codtit, codusu, nomeusu, situusu, codcco,
                   posans AS posans_atual,
                   '4-ATUALIZADO'::varchar AS posans_novo
            FROM cadusu
            WHERE situusu = 'ATIVO'
              AND COALESCE(TRIM(codcco), '') <> ''
              AND posans = '1-INCLUSAO'
            ORDER BY id
            {_limit()}
        """,
        apply_sql=f"""
            UPDATE cadusu SET
                posans = '4-ATUALIZADO',
                {_AUDIT}
            WHERE id = ANY(%s)
              AND situusu = 'ATIVO'
              AND COALESCE(TRIM(codcco), '') <> ''
              AND posans = '1-INCLUSAO'
            RETURNING id, codtit, codusu, nomeusu, posans
        """,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE situusu = 'ATIVO'
              AND COALESCE(TRIM(codcco), '') <> ''
              AND posans = '1-INCLUSAO'
        """,
    ),
    "inativo_cco_null_exclusao": FixPlan(
        rule_id="inativo_cco_null_exclusao",
        label="Ajustar POSANS para 4-ATUALIZADO",
        summary="Sem CCO não há exclusão SIB → posans = 4-ATUALIZADO.",
        fields=("posans",),
        preview_sql=f"""
            SELECT id, codtit, codusu, nomeusu, situusu, codcco,
                   posans AS posans_atual,
                   '4-ATUALIZADO'::varchar AS posans_novo
            FROM cadusu
            WHERE situusu = 'INATIVO'
              AND codcco IS NULL
              AND posans = '3-EXCLUSAO'
            ORDER BY id
            {_limit()}
        """,
        apply_sql=f"""
            UPDATE cadusu SET
                posans = '4-ATUALIZADO',
                {_AUDIT}
            WHERE id = ANY(%s)
              AND situusu = 'INATIVO'
              AND codcco IS NULL
              AND posans = '3-EXCLUSAO'
            RETURNING id, codtit, codusu, nomeusu, posans
        """,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE situusu = 'INATIVO'
              AND codcco IS NULL
              AND posans = '3-EXCLUSAO'
        """,
    ),
    "inativo_cco_null_inclusao": FixPlan(
        rule_id="inativo_cco_null_inclusao",
        label="Ajustar POSANS para 4-ATUALIZADO",
        summary="INATIVO não entra em inclusão SIB → posans = 4-ATUALIZADO.",
        fields=("posans",),
        preview_sql=f"""
            SELECT id, codtit, codusu, nomeusu, situusu, codcco,
                   posans AS posans_atual,
                   '4-ATUALIZADO'::varchar AS posans_novo
            FROM cadusu
            WHERE situusu = 'INATIVO'
              AND codcco IS NULL
              AND posans = '1-INCLUSAO'
            ORDER BY id
            {_limit()}
        """,
        apply_sql=f"""
            UPDATE cadusu SET
                posans = '4-ATUALIZADO',
                {_AUDIT}
            WHERE id = ANY(%s)
              AND situusu = 'INATIVO'
              AND codcco IS NULL
              AND posans = '1-INCLUSAO'
            RETURNING id, codtit, codusu, nomeusu, posans
        """,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE situusu = 'INATIVO'
              AND codcco IS NULL
              AND posans = '1-INCLUSAO'
        """,
    ),
    "alteracao_com_cco": FixPlan(
        rule_id="alteracao_com_cco",
        label="Ajustar POSANS para 4-ATUALIZADO",
        summary="2-ALTERACAO com CCO conciliado → posans = 4-ATUALIZADO.",
        fields=("posans",),
        preview_sql=f"""
            SELECT id, codtit, codusu, nomeusu, situusu, codcco, dataini,
                   posans AS posans_atual,
                   '4-ATUALIZADO'::varchar AS posans_novo
            FROM cadusu
            WHERE posans = '2-ALTERACAO'
              AND COALESCE(TRIM(codcco), '') <> ''
            ORDER BY id
            {_limit()}
        """,
        apply_sql=f"""
            UPDATE cadusu SET
                posans = '4-ATUALIZADO',
                {_AUDIT}
            WHERE id = ANY(%s)
              AND posans = '2-ALTERACAO'
              AND COALESCE(TRIM(codcco), '') <> ''
            RETURNING id, codtit, codusu, nomeusu, posans
        """,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE posans = '2-ALTERACAO'
              AND COALESCE(TRIM(codcco), '') <> ''
        """,
    ),
    "reinclusao_antiga_com_cco": FixPlan(
        rule_id="reinclusao_antiga_com_cco",
        label="Ajustar POSANS para 4-ATUALIZADO",
        summary="Reinclusão antiga (>90 dias) com CCO → posans = 4-ATUALIZADO.",
        fields=("posans",),
        preview_sql=f"""
            SELECT id, codtit, codusu, nomeusu, situusu, codcco, dataini,
                   posans AS posans_atual,
                   '4-ATUALIZADO'::varchar AS posans_novo
            FROM cadusu
            WHERE dataini < CURRENT_DATE - INTERVAL '90 days'
              AND posans = '8-REINCLUSAO'
              AND COALESCE(TRIM(codcco), '') <> ''
            ORDER BY id
            {_limit()}
        """,
        apply_sql=f"""
            UPDATE cadusu SET
                posans = '4-ATUALIZADO',
                {_AUDIT}
            WHERE id = ANY(%s)
              AND dataini < CURRENT_DATE - INTERVAL '90 days'
              AND posans = '8-REINCLUSAO'
              AND COALESCE(TRIM(codcco), '') <> ''
            RETURNING id, codtit, codusu, nomeusu, posans
        """,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE dataini < CURRENT_DATE - INTERVAL '90 days'
              AND posans = '8-REINCLUSAO'
              AND COALESCE(TRIM(codcco), '') <> ''
        """,
    ),
    "inclusao_antiga_com_cco": FixPlan(
        rule_id="inclusao_antiga_com_cco",
        label="Ajustar POSANS para 4-ATUALIZADO",
        summary="Inclusão antiga (>90 dias) com CCO → posans = 4-ATUALIZADO.",
        fields=("posans",),
        preview_sql=f"""
            SELECT id, codtit, codusu, nomeusu, situusu, codcco, dataini,
                   posans AS posans_atual,
                   '4-ATUALIZADO'::varchar AS posans_novo
            FROM cadusu
            WHERE dataini < CURRENT_DATE - INTERVAL '90 days'
              AND posans = '1-INCLUSAO'
              AND COALESCE(TRIM(codcco), '') <> ''
            ORDER BY id
            {_limit()}
        """,
        apply_sql=f"""
            UPDATE cadusu SET
                posans = '4-ATUALIZADO',
                {_AUDIT}
            WHERE id = ANY(%s)
              AND dataini < CURRENT_DATE - INTERVAL '90 days'
              AND posans = '1-INCLUSAO'
              AND COALESCE(TRIM(codcco), '') <> ''
            RETURNING id, codtit, codusu, nomeusu, posans
        """,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE dataini < CURRENT_DATE - INTERVAL '90 days'
              AND posans = '1-INCLUSAO'
              AND COALESCE(TRIM(codcco), '') <> ''
        """,
    ),
    "reinclusao_recente_com_cco": FixPlan(
        rule_id="reinclusao_recente_com_cco",
        label="Ajustar POSANS para 4-ATUALIZADO",
        summary="Reinclusão recente com CCO já existente → posans = 4-ATUALIZADO.",
        fields=("posans",),
        preview_sql=f"""
            SELECT id, codtit, codusu, nomeusu, situusu, codcco, dataini,
                   posans AS posans_atual,
                   '4-ATUALIZADO'::varchar AS posans_novo
            FROM cadusu
            WHERE dataini >= CURRENT_DATE - INTERVAL '90 days'
              AND posans = '8-REINCLUSAO'
              AND COALESCE(TRIM(codcco), '') <> ''
            ORDER BY id
            {_limit()}
        """,
        apply_sql=f"""
            UPDATE cadusu SET
                posans = '4-ATUALIZADO',
                {_AUDIT}
            WHERE id = ANY(%s)
              AND dataini >= CURRENT_DATE - INTERVAL '90 days'
              AND posans = '8-REINCLUSAO'
              AND COALESCE(TRIM(codcco), '') <> ''
            RETURNING id, codtit, codusu, nomeusu, posans
        """,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE dataini >= CURRENT_DATE - INTERVAL '90 days'
              AND posans = '8-REINCLUSAO'
              AND COALESCE(TRIM(codcco), '') <> ''
        """,
    ),
    "ativo_sem_cco_fora_inclusao": FixPlan(
        rule_id="ativo_sem_cco_fora_inclusao",
        label="Ajustar POSANS para 1-INCLUSAO",
        summary=(
            "ATIVO sem CCO com CPF → posans = 1-INCLUSAO. "
            "Não aplica sem CPF (ANS não acata inclusão sem CPF para gerar CCO)."
        ),
        fields=("posans",),
        preview_sql=f"""
            SELECT id, codtit, codusu, nomeusu, situusu, cpfusu, codcco,
                   posans AS posans_atual,
                   '1-INCLUSAO'::varchar AS posans_novo
            FROM cadusu
            WHERE situusu = 'ATIVO'
              AND COALESCE(TRIM(codcco), '') = ''
              AND COALESCE(TRIM(cpfusu), '') <> ''
              AND posans NOT IN ('1-INCLUSAO', '8-REINCLUSAO')
            ORDER BY id
            {_limit()}
        """,
        apply_sql=f"""
            UPDATE cadusu SET
                posans = '1-INCLUSAO',
                {_AUDIT}
            WHERE id = ANY(%s)
              AND situusu = 'ATIVO'
              AND COALESCE(TRIM(codcco), '') = ''
              AND COALESCE(TRIM(cpfusu), '') <> ''
              AND posans NOT IN ('1-INCLUSAO', '8-REINCLUSAO')
            RETURNING id, codtit, codusu, nomeusu, cpfusu, posans
        """,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE situusu = 'ATIVO'
              AND COALESCE(TRIM(codcco), '') = ''
              AND COALESCE(TRIM(cpfusu), '') <> ''
              AND posans NOT IN ('1-INCLUSAO', '8-REINCLUSAO')
        """,
    ),
    "ativo_com_cco_exclusao": FixPlan(
        rule_id="ativo_com_cco_exclusao",
        label="Ajustar POSANS para 4-ATUALIZADO",
        summary=(
            "ATIVO incompatível com 3-EXCLUSAO. Sugestão segura: cancelar o movimento "
            "e manter ATIVO com posans = 4-ATUALIZADO. Se a exclusão for intencional, "
            "trate situusu/datafim manualmente."
        ),
        fields=("posans",),
        preview_sql=f"""
            SELECT id, codtit, codusu, nomeusu, situusu, codcco, datafim,
                   posans AS posans_atual,
                   '4-ATUALIZADO'::varchar AS posans_novo
            FROM cadusu
            WHERE situusu = 'ATIVO'
              AND posans = '3-EXCLUSAO'
            ORDER BY id
            {_limit()}
        """,
        apply_sql=f"""
            UPDATE cadusu SET
                posans = '4-ATUALIZADO',
                {_AUDIT}
            WHERE id = ANY(%s)
              AND situusu = 'ATIVO'
              AND posans = '3-EXCLUSAO'
            RETURNING id, codtit, codusu, nomeusu, posans
        """,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE situusu = 'ATIVO'
              AND posans = '3-EXCLUSAO'
        """,
    ),
    "inativo_com_cco_nao_excluido": FixPlan(
        rule_id="inativo_com_cco_nao_excluido",
        label="Ajustar POSANS para 3-EXCLUSAO",
        summary="INATIVO com CCO pendente de baixa na ANS → posans = 3-EXCLUSAO.",
        fields=("posans",),
        preview_sql=f"""
            SELECT id, codtit, codusu, nomeusu, situusu, codcco, datafim,
                   posans AS posans_atual,
                   '3-EXCLUSAO'::varchar AS posans_novo
            FROM cadusu
            WHERE situusu = 'INATIVO'
              AND COALESCE(TRIM(codcco), '') <> ''
              AND posans NOT IN ('3-EXCLUSAO', '4-ATUALIZADO')
            ORDER BY id
            {_limit()}
        """,
        apply_sql=f"""
            UPDATE cadusu SET
                posans = '3-EXCLUSAO',
                {_AUDIT}
            WHERE id = ANY(%s)
              AND situusu = 'INATIVO'
              AND COALESCE(TRIM(codcco), '') <> ''
              AND posans NOT IN ('3-EXCLUSAO', '4-ATUALIZADO')
            RETURNING id, codtit, codusu, nomeusu, posans
        """,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE situusu = 'INATIVO'
              AND COALESCE(TRIM(codcco), '') <> ''
              AND posans NOT IN ('3-EXCLUSAO', '4-ATUALIZADO')
        """,
    ),
    "exclusao_sem_datafim_nao_inativo": FixPlan(
        rule_id="exclusao_sem_datafim_nao_inativo",
        label="Ajustar POSANS para 4-ATUALIZADO",
        summary=(
            "Erro de cadastro (bloqueio com 3-EXCLUSAO indevida): "
            "situusu ≠ INATIVO + CODCCO válido → posans = 4-ATUALIZADO."
        ),
        fields=("posans",),
        preview_sql=f"""
            SELECT id, codtit, codusu, nomeusu, situusu, codcco, datafim,
                   posans AS posans_atual,
                   '4-ATUALIZADO'::varchar AS posans_novo
            FROM cadusu
            WHERE situusu <> 'INATIVO'
              AND posans = '3-EXCLUSAO'
              AND datafim IS NULL
              AND COALESCE(TRIM(codcco), '') <> ''
            ORDER BY id
            {_limit()}
        """,
        apply_sql=f"""
            UPDATE cadusu SET
                posans = '4-ATUALIZADO',
                {_AUDIT}
            WHERE id = ANY(%s)
              AND situusu <> 'INATIVO'
              AND posans = '3-EXCLUSAO'
              AND datafim IS NULL
              AND COALESCE(TRIM(codcco), '') <> ''
            RETURNING id, codtit, codusu, nomeusu, situusu, posans
        """,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE situusu <> 'INATIVO'
              AND posans = '3-EXCLUSAO'
              AND datafim IS NULL
              AND COALESCE(TRIM(codcco), '') <> ''
        """,
    ),
    "inclusao_sem_dataini": FixPlan(
        rule_id="inclusao_sem_dataini",
        label="Preencher DATAINI",
        summary="Inclusão/reinclusão sem DATAINI → dataini = COALESCE(datacad, CURRENT_DATE).",
        fields=("dataini",),
        preview_sql=f"""
            SELECT id, codtit, codusu, nomeusu, situusu, posans, datacad,
                   dataini AS dataini_atual,
                   COALESCE(datacad, CURRENT_DATE) AS dataini_novo
            FROM cadusu
            WHERE posans IN ('1-INCLUSAO', '8-REINCLUSAO')
              AND dataini IS NULL
            ORDER BY id
            {_limit()}
        """,
        apply_sql=f"""
            UPDATE cadusu SET
                dataini = COALESCE(datacad, CURRENT_DATE),
                {_AUDIT}
            WHERE id = ANY(%s)
              AND posans IN ('1-INCLUSAO', '8-REINCLUSAO')
              AND dataini IS NULL
            RETURNING id, codtit, codusu, nomeusu, dataini
        """,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE posans IN ('1-INCLUSAO', '8-REINCLUSAO')
              AND dataini IS NULL
        """,
    ),
    "cpf_invalido_ativo": FixPlan(
        rule_id="cpf_invalido_ativo",
        label="Normalizar CPF (somente dígitos)",
        summary=(
            "Remove máscara do CPF quando o resultado tiver 11 dígitos. "
            "CPFs que não normalizam para 11 dígitos ficam de fora (correção manual)."
        ),
        fields=("cpfusu",),
        preview_sql=f"""
            SELECT id, codtit, codusu, nomeusu, situusu,
                   cpfusu AS cpfusu_atual,
                   REGEXP_REPLACE(cpfusu, '[^0-9]', '', 'g') AS cpfusu_novo
            FROM cadusu
            WHERE situusu = 'ATIVO'
              AND COALESCE(TRIM(cpfusu), '') <> ''
              AND (
                    LENGTH(REGEXP_REPLACE(cpfusu, '[^0-9]', '', 'g')) <> 11
                 OR cpfusu !~ '^[0-9]{{11}}$'
              )
              AND LENGTH(REGEXP_REPLACE(cpfusu, '[^0-9]', '', 'g')) = 11
            ORDER BY id
            {_limit()}
        """,
        apply_sql=f"""
            UPDATE cadusu SET
                cpfusu = REGEXP_REPLACE(cpfusu, '[^0-9]', '', 'g'),
                {_AUDIT}
            WHERE id = ANY(%s)
              AND situusu = 'ATIVO'
              AND COALESCE(TRIM(cpfusu), '') <> ''
              AND LENGTH(REGEXP_REPLACE(cpfusu, '[^0-9]', '', 'g')) = 11
              AND cpfusu !~ '^[0-9]{{11}}$'
            RETURNING id, codtit, codusu, nomeusu, cpfusu
        """,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE situusu = 'ATIVO'
              AND COALESCE(TRIM(cpfusu), '') <> ''
              AND (
                    LENGTH(REGEXP_REPLACE(cpfusu, '[^0-9]', '', 'g')) <> 11
                 OR cpfusu !~ '^[0-9]{11}$'
              )
              AND LENGTH(REGEXP_REPLACE(cpfusu, '[^0-9]', '', 'g')) = 11
        """,
    ),
    "divergencia_nome_cadusu_confsib": FixPlan(
        rule_id="divergencia_nome_cadusu_confsib",
        label="Enviar nome à ANS (SIB-FLEX)",
        summary=(
            "situusu ≠ INATIVO: posans = 10-SIB-FLEX e ansnome = 1 "
            "(qualquer codusu; anstitular não é usado)."
        ),
        fields=("posans", "ansnome"),
        preview_sql=f"""
            SELECT DISTINCT ON (c.id)
                   c.id, c.codtit, c.codusu, c.codcco, c.situusu,
                   c.nomeusu AS nome_local, s.nomeusu AS nome_ans,
                   c.posans AS posans_atual,
                   '10-SIB-FLEX'::varchar AS posans_novo,
                   c.ansnome AS ansnome_atual,
                   '1'::varchar AS ansnome_novo
            FROM cadusu c
            INNER JOIN confsib s ON s.codcco = c.codcco
            WHERE COALESCE(c.codcco, '') <> ''
              AND c.situusu <> 'INATIVO'
              AND UPPER(TRIM(COALESCE(c.nomeusu, '')))
                  <> UPPER(TRIM(COALESCE(s.nomeusu, '')))
              AND NOT (
                    c.posans = '10-SIB-FLEX'
                AND COALESCE(TRIM(c.ansnome), '') = '1'
              )
            ORDER BY c.id, s.numseq DESC
            {_limit()}
        """,
        apply_sql=f"""
            UPDATE cadusu c SET
                posans = '10-SIB-FLEX',
                ansnome = '1',
                {_AUDIT}
            WHERE c.id = ANY(%s)
              AND COALESCE(c.codcco, '') <> ''
              AND c.situusu <> 'INATIVO'
              AND NOT (
                    c.posans = '10-SIB-FLEX'
                AND COALESCE(TRIM(c.ansnome), '') = '1'
              )
              AND EXISTS (
                SELECT 1 FROM confsib s
                WHERE s.codcco = c.codcco
                  AND UPPER(TRIM(COALESCE(c.nomeusu, '')))
                      <> UPPER(TRIM(COALESCE(s.nomeusu, '')))
              )
            RETURNING c.id, c.codtit, c.codusu, c.nomeusu, c.posans, c.ansnome
        """,
        count_sql="""
            SELECT COUNT(DISTINCT c.id) AS total
            FROM cadusu c
            INNER JOIN confsib s ON s.codcco = c.codcco
            WHERE COALESCE(c.codcco, '') <> ''
              AND c.situusu <> 'INATIVO'
              AND UPPER(TRIM(COALESCE(c.nomeusu, '')))
                  <> UPPER(TRIM(COALESCE(s.nomeusu, '')))
              AND NOT (
                    c.posans = '10-SIB-FLEX'
                AND COALESCE(TRIM(c.ansnome), '') = '1'
              )
        """,
    ),
    "divergencia_nome_inativo_confsib": FixPlan(
        rule_id="divergencia_nome_inativo_confsib",
        label="Acatar nome da ANS (confsib)",
        summary=(
            "INATIVO: atualiza cadusu.nomeusu com o nome da confsib "
            "(base local acata a ANS)."
        ),
        fields=("nomeusu",),
        preview_sql=f"""
            SELECT DISTINCT ON (c.id)
                   c.id, c.codtit, c.codusu, c.codcco, c.situusu, c.posans,
                   c.nomeusu AS nomeusu_atual,
                   LEFT(TRIM(s.nomeusu), 80) AS nomeusu_novo,
                   s.nomeusu AS nome_ans
            FROM cadusu c
            INNER JOIN confsib s ON s.codcco = c.codcco
            WHERE COALESCE(c.codcco, '') <> ''
              AND c.situusu = 'INATIVO'
              AND UPPER(TRIM(COALESCE(c.nomeusu, '')))
                  <> UPPER(TRIM(COALESCE(s.nomeusu, '')))
              AND COALESCE(TRIM(s.nomeusu), '') <> ''
            ORDER BY c.id, s.numseq DESC
            {_limit()}
        """,
        apply_sql=f"""
            UPDATE cadusu c SET
                nomeusu = sub.nome_novo,
                {_AUDIT}
            FROM (
                SELECT DISTINCT ON (c2.id)
                       c2.id,
                       LEFT(TRIM(s.nomeusu), 80) AS nome_novo
                FROM cadusu c2
                INNER JOIN confsib s ON s.codcco = c2.codcco
                WHERE c2.id = ANY(%s)
                  AND COALESCE(c2.codcco, '') <> ''
                  AND c2.situusu = 'INATIVO'
                  AND UPPER(TRIM(COALESCE(c2.nomeusu, '')))
                      <> UPPER(TRIM(COALESCE(s.nomeusu, '')))
                  AND COALESCE(TRIM(s.nomeusu), '') <> ''
                ORDER BY c2.id, s.numseq DESC
            ) sub
            WHERE c.id = sub.id
            RETURNING c.id, c.codtit, c.codusu, c.nomeusu, c.situusu
        """,
        count_sql="""
            SELECT COUNT(DISTINCT c.id) AS total
            FROM cadusu c
            INNER JOIN confsib s ON s.codcco = c.codcco
            WHERE COALESCE(c.codcco, '') <> ''
              AND c.situusu = 'INATIVO'
              AND UPPER(TRIM(COALESCE(c.nomeusu, '')))
                  <> UPPER(TRIM(COALESCE(s.nomeusu, '')))
              AND COALESCE(TRIM(s.nomeusu), '') <> ''
        """,
    ),
    "divergencia_nasc_cadusu_confsib": FixPlan(
        rule_id="divergencia_nasc_cadusu_confsib",
        label="Enviar nascimento à ANS (SIB-FLEX)",
        summary=(
            "situusu ≠ INATIVO, mesmo registro (CCO+DATAINI+nome+CPF): "
            "posans = 10-SIB-FLEX e ansnasc = 1 para atualizar nascimento na ANS."
        ),
        fields=("posans", "ansnasc"),
        preview_sql=f"""
            SELECT DISTINCT ON (c.id)
                   c.id, c.codtit, c.codusu, c.codcco, c.situusu,
                   c.nomeusu, c.cpfusu, c.dataini,
                   c.nascusu AS nasc_local,
                   CASE
                     WHEN TRIM(s.nascusu) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$'
                       THEN TRIM(s.nascusu)::date
                     WHEN TRIM(s.nascusu) ~ '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}$'
                       THEN to_date(TRIM(s.nascusu), 'DD/MM/YYYY')
                     ELSE NULL
                   END AS nasc_ans,
                   c.posans AS posans_atual,
                   '10-SIB-FLEX'::varchar AS posans_novo,
                   c.ansnasc AS ansnasc_atual,
                   '1'::varchar AS ansnasc_novo
            FROM cadusu c
            INNER JOIN confsib s ON s.codcco = c.codcco
            WHERE c.situusu <> 'INATIVO'
              AND COALESCE(c.codcco, '') <> ''
              AND c.dataini IS NOT NULL
              AND CASE
                    WHEN NULLIF(TRIM(s.dataini), '') IS NULL THEN NULL
                    WHEN TRIM(s.dataini) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$'
                      THEN TRIM(s.dataini)::date
                    WHEN TRIM(s.dataini) ~ '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}$'
                      THEN to_date(TRIM(s.dataini), 'DD/MM/YYYY')
                    ELSE NULL
                  END = c.dataini
              AND COALESCE(TRIM(c.cpfusu), '') <> ''
              AND TRIM(s.cpfusu) = TRIM(c.cpfusu)
              AND COALESCE(TRIM(c.nomeusu), '') <> ''
              AND UPPER(TRIM(COALESCE(s.nomeusu, ''))) = UPPER(TRIM(c.nomeusu))
              AND c.nascusu IS NOT NULL
              AND CASE
                    WHEN TRIM(s.nascusu) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$'
                      THEN TRIM(s.nascusu)::date
                    WHEN TRIM(s.nascusu) ~ '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}$'
                      THEN to_date(TRIM(s.nascusu), 'DD/MM/YYYY')
                    ELSE NULL
                  END IS NOT NULL
              AND CASE
                    WHEN TRIM(s.nascusu) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$'
                      THEN TRIM(s.nascusu)::date
                    WHEN TRIM(s.nascusu) ~ '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}$'
                      THEN to_date(TRIM(s.nascusu), 'DD/MM/YYYY')
                    ELSE NULL
                  END <> c.nascusu
              AND NOT (
                    c.posans = '10-SIB-FLEX'
                AND COALESCE(TRIM(c.ansnasc), '') = '1'
              )
            ORDER BY c.id, s.numseq DESC
            {_limit()}
        """,
        apply_sql=f"""
            UPDATE cadusu c SET
                posans = '10-SIB-FLEX',
                ansnasc = '1',
                {_AUDIT}
            WHERE c.id = ANY(%s)
              AND c.situusu <> 'INATIVO'
              AND COALESCE(c.codcco, '') <> ''
              AND NOT (
                    c.posans = '10-SIB-FLEX'
                AND COALESCE(TRIM(c.ansnasc), '') = '1'
              )
              AND EXISTS (
                SELECT 1 FROM confsib s
                WHERE s.codcco = c.codcco
                  AND c.dataini IS NOT NULL
                  AND CASE
                        WHEN NULLIF(TRIM(s.dataini), '') IS NULL THEN NULL
                        WHEN TRIM(s.dataini) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$'
                          THEN TRIM(s.dataini)::date
                        WHEN TRIM(s.dataini) ~ '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}$'
                          THEN to_date(TRIM(s.dataini), 'DD/MM/YYYY')
                        ELSE NULL
                      END = c.dataini
                  AND COALESCE(TRIM(c.cpfusu), '') <> ''
                  AND TRIM(s.cpfusu) = TRIM(c.cpfusu)
                  AND COALESCE(TRIM(c.nomeusu), '') <> ''
                  AND UPPER(TRIM(COALESCE(s.nomeusu, ''))) = UPPER(TRIM(c.nomeusu))
                  AND c.nascusu IS NOT NULL
                  AND CASE
                        WHEN TRIM(s.nascusu) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$'
                          THEN TRIM(s.nascusu)::date
                        WHEN TRIM(s.nascusu) ~ '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}$'
                          THEN to_date(TRIM(s.nascusu), 'DD/MM/YYYY')
                        ELSE NULL
                      END IS NOT NULL
                  AND CASE
                        WHEN TRIM(s.nascusu) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$'
                          THEN TRIM(s.nascusu)::date
                        WHEN TRIM(s.nascusu) ~ '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}$'
                          THEN to_date(TRIM(s.nascusu), 'DD/MM/YYYY')
                        ELSE NULL
                      END <> c.nascusu
              )
            RETURNING c.id, c.codtit, c.codusu, c.nascusu, c.posans, c.ansnasc
        """,
        count_sql="""
            SELECT COUNT(DISTINCT c.id) AS total
            FROM cadusu c
            INNER JOIN confsib s ON s.codcco = c.codcco
            WHERE c.situusu <> 'INATIVO'
              AND COALESCE(c.codcco, '') <> ''
              AND c.dataini IS NOT NULL
              AND CASE
                    WHEN NULLIF(TRIM(s.dataini), '') IS NULL THEN NULL
                    WHEN TRIM(s.dataini) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                      THEN TRIM(s.dataini)::date
                    WHEN TRIM(s.dataini) ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}$'
                      THEN to_date(TRIM(s.dataini), 'DD/MM/YYYY')
                    ELSE NULL
                  END = c.dataini
              AND COALESCE(TRIM(c.cpfusu), '') <> ''
              AND TRIM(s.cpfusu) = TRIM(c.cpfusu)
              AND COALESCE(TRIM(c.nomeusu), '') <> ''
              AND UPPER(TRIM(COALESCE(s.nomeusu, ''))) = UPPER(TRIM(c.nomeusu))
              AND c.nascusu IS NOT NULL
              AND CASE
                    WHEN TRIM(s.nascusu) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                      THEN TRIM(s.nascusu)::date
                    WHEN TRIM(s.nascusu) ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}$'
                      THEN to_date(TRIM(s.nascusu), 'DD/MM/YYYY')
                    ELSE NULL
                  END IS NOT NULL
              AND CASE
                    WHEN TRIM(s.nascusu) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                      THEN TRIM(s.nascusu)::date
                    WHEN TRIM(s.nascusu) ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}$'
                      THEN to_date(TRIM(s.nascusu), 'DD/MM/YYYY')
                    ELSE NULL
                  END <> c.nascusu
              AND NOT (
                    c.posans = '10-SIB-FLEX'
                AND COALESCE(TRIM(c.ansnasc), '') = '1'
              )
        """,
    ),
    "cpf_invalido_cruzado_nascimento": FixPlan(
        rule_id="cpf_invalido_cruzado_nascimento",
        label="Limpar CPF (NULL)",
        summary=(
            "Zera cpfusu nos cadastros em que o CPF não confere com o nascimento "
            "(mantém o CPF no beneficiário mais antigo do grupo / titular)."
        ),
        fields=("cpfusu",),
        preview_sql=f"""
            WITH base AS (
                SELECT id, codtit, codusu, nomeusu, cpfusu, nascusu,
                       posans, codcco,
                       LEFT(codtit, 4) AS empresa,
                       TRIM(cpfusu) AS cpf
                FROM cadusu
                WHERE situusu = 'ATIVO'
                  AND COALESCE(TRIM(cpfusu), '') <> ''
                  AND cpfusu ~ '^[0-9]{{11}}$'
                  AND LENGTH(COALESCE(codtit, '')) >= 4
            ),
            grupos AS (
                SELECT empresa, cpf
                FROM base
                GROUP BY empresa, cpf
                HAVING COUNT(*) > 1
                   AND (
                        MIN(nascusu) IS DISTINCT FROM MAX(nascusu)
                     OR (
                            COUNT(*) FILTER (WHERE nascusu IS NULL) > 0
                        AND COUNT(*) FILTER (WHERE nascusu IS NOT NULL) > 0
                     )
                   )
            ),
            keepers AS (
                SELECT DISTINCT ON (b.empresa, b.cpf)
                       b.id AS id_mantido, b.empresa, b.cpf,
                       b.nomeusu AS nome_mantido, b.nascusu AS nasc_mantido
                FROM base b
                INNER JOIN grupos g ON g.empresa = b.empresa AND g.cpf = b.cpf
                ORDER BY b.empresa, b.cpf,
                         b.nascusu ASC NULLS LAST,
                         CASE WHEN b.codusu = '00' THEN 0 ELSE 1 END,
                         b.id
            )
            SELECT b.id, b.empresa, b.codtit, b.codusu, b.nomeusu,
                   b.codcco, b.posans, b.nascusu,
                   b.cpfusu AS cpfusu_atual,
                   NULL::varchar AS cpfusu_novo,
                   k.id_mantido, k.nome_mantido, k.nasc_mantido
            FROM base b
            INNER JOIN grupos g ON g.empresa = b.empresa AND g.cpf = b.cpf
            INNER JOIN keepers k ON k.empresa = b.empresa AND k.cpf = b.cpf
            WHERE b.id <> k.id_mantido
            ORDER BY b.cpf, b.id
            {_limit()}
        """,
        apply_sql=f"""
            UPDATE cadusu c SET
                cpfusu = NULL,
                {_AUDIT}
            WHERE c.id = ANY(%s)
              AND c.id IN (
                WITH base AS (
                    SELECT id, codtit, codusu, cpfusu, nascusu,
                           LEFT(codtit, 4) AS empresa,
                           TRIM(cpfusu) AS cpf
                    FROM cadusu
                    WHERE situusu = 'ATIVO'
                      AND COALESCE(TRIM(cpfusu), '') <> ''
                      AND cpfusu ~ '^[0-9]{{11}}$'
                      AND LENGTH(COALESCE(codtit, '')) >= 4
                ),
                grupos AS (
                    SELECT empresa, cpf
                    FROM base
                    GROUP BY empresa, cpf
                    HAVING COUNT(*) > 1
                       AND (
                            MIN(nascusu) IS DISTINCT FROM MAX(nascusu)
                         OR (
                                COUNT(*) FILTER (WHERE nascusu IS NULL) > 0
                            AND COUNT(*) FILTER (WHERE nascusu IS NOT NULL) > 0
                         )
                       )
                ),
                keepers AS (
                    SELECT DISTINCT ON (b.empresa, b.cpf)
                           b.id AS id_mantido, b.empresa, b.cpf
                    FROM base b
                    INNER JOIN grupos g ON g.empresa = b.empresa AND g.cpf = b.cpf
                    ORDER BY b.empresa, b.cpf,
                             b.nascusu ASC NULLS LAST,
                             CASE WHEN b.codusu = '00' THEN 0 ELSE 1 END,
                             b.id
                )
                SELECT b.id
                FROM base b
                INNER JOIN grupos g ON g.empresa = b.empresa AND g.cpf = b.cpf
                INNER JOIN keepers k ON k.empresa = b.empresa AND k.cpf = b.cpf
                WHERE b.id <> k.id_mantido
              )
            RETURNING c.id, c.codtit, c.codusu, c.nomeusu, c.cpfusu, c.nascusu
        """,
        count_sql="""
            WITH base AS (
                SELECT id, codtit, codusu, cpfusu, nascusu,
                       LEFT(codtit, 4) AS empresa,
                       TRIM(cpfusu) AS cpf
                FROM cadusu
                WHERE situusu = 'ATIVO'
                  AND COALESCE(TRIM(cpfusu), '') <> ''
                  AND cpfusu ~ '^[0-9]{11}$'
                  AND LENGTH(COALESCE(codtit, '')) >= 4
            ),
            grupos AS (
                SELECT empresa, cpf
                FROM base
                GROUP BY empresa, cpf
                HAVING COUNT(*) > 1
                   AND (
                        MIN(nascusu) IS DISTINCT FROM MAX(nascusu)
                     OR (
                            COUNT(*) FILTER (WHERE nascusu IS NULL) > 0
                        AND COUNT(*) FILTER (WHERE nascusu IS NOT NULL) > 0
                     )
                   )
            ),
            keepers AS (
                SELECT DISTINCT ON (b.empresa, b.cpf)
                       b.id AS id_mantido, b.empresa, b.cpf
                FROM base b
                INNER JOIN grupos g ON g.empresa = b.empresa AND g.cpf = b.cpf
                ORDER BY b.empresa, b.cpf,
                         b.nascusu ASC NULLS LAST,
                         CASE WHEN b.codusu = '00' THEN 0 ELSE 1 END,
                         b.id
            )
            SELECT COUNT(*) AS total
            FROM base b
            INNER JOIN grupos g ON g.empresa = b.empresa AND g.cpf = b.cpf
            INNER JOIN keepers k ON k.empresa = b.empresa AND k.cpf = b.cpf
            WHERE b.id <> k.id_mantido
        """,
    ),
    "cadusu_sem_codans": FixPlan(
        rule_id="cadusu_sem_codans",
        label="Preencher CODANS (confsib ou montado)",
        summary=(
            "1) INATIVO com CODCCO+CPF+DATAINI na confsib → copia confsib.codusu. "
            "2) Sem match → monta CODANS = codtit || '-' || codusu "
            "(ex.: 2741-0001-01)."
        ),
        fields=("codans",),
        preview_sql=f"""
            WITH conf_match AS (
                SELECT DISTINCT ON (c.id)
                       c.id,
                       LEFT(TRIM(s.codusu), 30) AS codans_conf
                FROM cadusu c
                INNER JOIN confsib s
                  ON TRIM(s.codcco) = TRIM(c.codcco)
                 AND TRIM(s.cpfusu) = TRIM(c.cpfusu)
                 AND COALESCE(TRIM(s.codusu), '') <> ''
                 AND (
                       CASE
                         WHEN NULLIF(TRIM(s.dataini), '') IS NULL THEN NULL
                         WHEN TRIM(s.dataini) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$'
                           THEN TRIM(s.dataini)::date
                         WHEN TRIM(s.dataini) ~ '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}$'
                           THEN to_date(TRIM(s.dataini), 'DD/MM/YYYY')
                         ELSE NULL
                       END
                     ) = c.dataini
                WHERE COALESCE(TRIM(c.codans), '') = ''
                  AND c.situusu = 'INATIVO'
                  AND COALESCE(TRIM(c.codcco), '') <> ''
                  AND COALESCE(TRIM(c.cpfusu), '') <> ''
                  AND c.dataini IS NOT NULL
                ORDER BY c.id, s.numseq DESC
            ),
            proposta AS (
                SELECT c.id, c.codtit, c.codusu, c.nomeusu, c.situusu, c.posans,
                       c.codcco, c.cpfusu, c.dataini,
                       c.codans AS codans_atual,
                       CASE
                         WHEN cm.codans_conf IS NOT NULL THEN cm.codans_conf
                         WHEN COALESCE(TRIM(c.codtit), '') <> ''
                          AND COALESCE(TRIM(c.codusu), '') <> ''
                           THEN LEFT(TRIM(c.codtit) || '-' || TRIM(c.codusu), 30)
                         ELSE NULL
                       END AS codans_novo,
                       CASE
                         WHEN cm.codans_conf IS NOT NULL THEN 'confsib'
                         WHEN COALESCE(TRIM(c.codtit), '') <> ''
                          AND COALESCE(TRIM(c.codusu), '') <> ''
                           THEN 'montado'
                         ELSE NULL
                       END AS origem
                FROM cadusu c
                LEFT JOIN conf_match cm ON cm.id = c.id
                WHERE COALESCE(TRIM(c.codans), '') = ''
            )
            SELECT id, codtit, codusu, nomeusu, situusu, posans,
                   codcco, cpfusu, dataini,
                   codans_atual, codans_novo, origem
            FROM proposta
            WHERE COALESCE(TRIM(codans_novo), '') <> ''
            ORDER BY origem, id
            {_limit()}
        """,
        apply_sql=f"""
            UPDATE cadusu c SET
                codans = sub.codans_novo,
                {_AUDIT}
            FROM (
                WITH alvo AS (
                    SELECT c3.id, c3.codtit, c3.codusu, c3.situusu,
                           c3.codcco, c3.cpfusu, c3.dataini, c3.codans
                    FROM cadusu c3
                    WHERE c3.id = ANY(%s)
                      AND COALESCE(TRIM(c3.codans), '') = ''
                ),
                conf_match AS (
                    SELECT DISTINCT ON (a.id)
                           a.id,
                           LEFT(TRIM(s.codusu), 30) AS codans_conf
                    FROM alvo a
                    INNER JOIN confsib s
                      ON TRIM(s.codcco) = TRIM(a.codcco)
                     AND TRIM(s.cpfusu) = TRIM(a.cpfusu)
                     AND COALESCE(TRIM(s.codusu), '') <> ''
                     AND (
                           CASE
                             WHEN NULLIF(TRIM(s.dataini), '') IS NULL THEN NULL
                             WHEN TRIM(s.dataini) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$'
                               THEN TRIM(s.dataini)::date
                             WHEN TRIM(s.dataini) ~ '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}$'
                               THEN to_date(TRIM(s.dataini), 'DD/MM/YYYY')
                             ELSE NULL
                           END
                         ) = a.dataini
                    WHERE a.situusu = 'INATIVO'
                      AND COALESCE(TRIM(a.codcco), '') <> ''
                      AND COALESCE(TRIM(a.cpfusu), '') <> ''
                      AND a.dataini IS NOT NULL
                    ORDER BY a.id, s.numseq DESC
                )
                SELECT a.id,
                       CASE
                         WHEN cm.codans_conf IS NOT NULL THEN cm.codans_conf
                         WHEN COALESCE(TRIM(a.codtit), '') <> ''
                          AND COALESCE(TRIM(a.codusu), '') <> ''
                           THEN LEFT(TRIM(a.codtit) || '-' || TRIM(a.codusu), 30)
                         ELSE NULL
                       END AS codans_novo
                FROM alvo a
                LEFT JOIN conf_match cm ON cm.id = a.id
            ) sub
            WHERE c.id = sub.id
              AND COALESCE(TRIM(sub.codans_novo), '') <> ''
            RETURNING c.id, c.codtit, c.codusu, c.nomeusu, c.codans, c.situusu
        """,
        count_sql="""
            WITH conf_match AS (
                SELECT DISTINCT c.id
                FROM cadusu c
                INNER JOIN confsib s
                  ON TRIM(s.codcco) = TRIM(c.codcco)
                 AND TRIM(s.cpfusu) = TRIM(c.cpfusu)
                 AND COALESCE(TRIM(s.codusu), '') <> ''
                 AND (
                       CASE
                         WHEN NULLIF(TRIM(s.dataini), '') IS NULL THEN NULL
                         WHEN TRIM(s.dataini) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                           THEN TRIM(s.dataini)::date
                         WHEN TRIM(s.dataini) ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}$'
                           THEN to_date(TRIM(s.dataini), 'DD/MM/YYYY')
                         ELSE NULL
                       END
                     ) = c.dataini
                WHERE COALESCE(TRIM(c.codans), '') = ''
                  AND c.situusu = 'INATIVO'
                  AND COALESCE(TRIM(c.codcco), '') <> ''
                  AND COALESCE(TRIM(c.cpfusu), '') <> ''
                  AND c.dataini IS NOT NULL
            )
            SELECT COUNT(*) AS total
            FROM cadusu c
            WHERE COALESCE(TRIM(c.codans), '') = ''
              AND (
                    c.id IN (SELECT id FROM conf_match)
                 OR (
                        COALESCE(TRIM(c.codtit), '') <> ''
                    AND COALESCE(TRIM(c.codusu), '') <> ''
                 )
              )
        """,
    ),
    "ativo_sem_cpf_posans": FixPlan(
        rule_id="ativo_sem_cpf_posans",
        label="Ajustar POSANS para 4-ATUALIZADO",
        summary="ATIVO sem CPF → posans = 4-ATUALIZADO.",
        fields=("posans",),
        preview_sql=f"""
            SELECT id, codtit, codusu, nomeusu, situusu, cpfusu, codcco,
                   posans AS posans_atual,
                   '4-ATUALIZADO'::varchar AS posans_novo
            FROM cadusu
            WHERE situusu = 'ATIVO'
              AND COALESCE(TRIM(cpfusu), '') = ''
            ORDER BY id
            {_limit()}
        """,
        apply_sql=f"""
            UPDATE cadusu SET
                posans = '4-ATUALIZADO',
                {_AUDIT}
            WHERE id = ANY(%s)
              AND situusu = 'ATIVO'
              AND COALESCE(TRIM(cpfusu), '') = ''
            RETURNING id, codtit, codusu, nomeusu, situusu, cpfusu, posans
        """,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE situusu = 'ATIVO'
              AND COALESCE(TRIM(cpfusu), '') = ''
        """,
    ),
    "ret_reativ_com_cco": FixPlan(
        rule_id="ret_reativ_com_cco",
        label="Ajustar POSANS para 4-ATUALIZADO",
        summary=(
            "9-RET REATIV com CCO e situusu ≠ INATIVO → posans = 4-ATUALIZADO "
            "(reativação conciliada com a ANS)."
        ),
        fields=("posans",),
        preview_sql=f"""
            SELECT id, codtit, codusu, nomeusu, situusu, codcco,
                   posans AS posans_atual,
                   '4-ATUALIZADO'::varchar AS posans_novo
            FROM cadusu
            WHERE posans = '9-RET REATIV'
              AND situusu <> 'INATIVO'
              AND COALESCE(TRIM(codcco), '') <> ''
            ORDER BY id
            {_limit()}
        """,
        apply_sql=f"""
            UPDATE cadusu SET
                posans = '4-ATUALIZADO',
                {_AUDIT}
            WHERE id = ANY(%s)
              AND posans = '9-RET REATIV'
              AND situusu <> 'INATIVO'
              AND COALESCE(TRIM(codcco), '') <> ''
            RETURNING id, codtit, codusu, nomeusu, situusu, codcco, posans
        """,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE posans = '9-RET REATIV'
              AND situusu <> 'INATIVO'
              AND COALESCE(TRIM(codcco), '') <> ''
        """,
    ),
    "sib_flex_sem_campo_marcado": FixPlan(
        rule_id="sib_flex_sem_campo_marcado",
        label="Marcar flags ANS pelas divergências confsib",
        summary=(
            "Compara cadusu × confsib (CODCCO) e seta = 1 cada flag cujo campo "
            "local diverge (ansrg, anscpf, ansmae, anscns, ansnasc, ansparentesco, "
            "ansnome, ansplano, ansdataini, ansdatafim). "
            "anstitular e anscnpjcei ficam de fora (sem espelho na confsib)."
        ),
        fields=(
            "ansrg",
            "anscpf",
            "ansmae",
            "anscns",
            "ansnasc",
            "ansparentesco",
            "ansnome",
            "ansplano",
            "ansdataini",
            "ansdatafim",
        ),
        preview_sql=f"""
            SELECT c.id, c.codtit, c.codusu, c.nomeusu, c.situusu, c.codcco,
                   {SIB_FLEX_PREVIEW_FLAGS}
            FROM cadusu c
            {CONFSIB_LATERAL}
            WHERE c.posans = '10-SIB-FLEX'
              AND NOT ({ANS_FLEX_ALGUM_MARCADO_C})
              AND ({SIB_FLEX_ALGUM_DIFF})
            ORDER BY c.id
            {_limit()}
        """,
        apply_sql=f"""
            UPDATE cadusu c SET
                {SIB_FLEX_FLAG_CASE},
                {_AUDIT}
            FROM confsib s
            WHERE c.id = ANY(%s)
              AND c.posans = '10-SIB-FLEX'
              AND NOT ({ANS_FLEX_ALGUM_MARCADO_C})
              AND s.codcco = c.codcco
              AND s.numseq = (
                    SELECT MAX(s2.numseq) FROM confsib s2
                    WHERE s2.codcco = c.codcco
              )
              AND ({SIB_FLEX_ALGUM_DIFF})
            RETURNING c.id, c.codtit, c.codusu, c.posans,
                      c.ansrg, c.anscpf, c.ansmae, c.anscns, c.ansnasc,
                      c.ansparentesco, c.ansnome, c.ansplano,
                      c.ansdataini, c.ansdatafim
        """,
        count_sql=f"""
            SELECT COUNT(*) AS total
            FROM cadusu c
            {CONFSIB_LATERAL}
            WHERE c.posans = '10-SIB-FLEX'
              AND NOT ({ANS_FLEX_ALGUM_MARCADO_C})
              AND ({SIB_FLEX_ALGUM_DIFF})
        """,
    ),
    "ativo_campos_sib_obrigatorios": FixPlan(
        rule_id="ativo_campos_sib_obrigatorios",
        label="Completar com confsib e ajustar POSANS",
        summary=(
            "Match preciso (cpfusu + dataini + nomeusu + nascusu): copia lacunas "
            "da confsib. Tudo preenchido com CODCCO → 4-ATUALIZADO; "
            "tudo preenchido sem CODCCO → 1-INCLUSAO."
        ),
        fields=("nomeusu", "nascusu", "sexousu", "cpfusu", "cns", "codcco", "posans"),
        preview_sql=f"""
            SELECT c.id, c.codtit, c.codusu, c.situusu,
                   c.nomeusu AS nome_atual,
                   CASE WHEN COALESCE(TRIM(c.nomeusu), '') = ''
                        THEN NULLIF(TRIM(s.nomeusu), '')
                        ELSE c.nomeusu END AS nome_novo,
                   c.nascusu AS nasc_atual,
                   COALESCE(c.nascusu, {NASC_CONFSIB}) AS nasc_novo,
                   c.sexousu AS sexo_atual,
                   CASE WHEN COALESCE(TRIM(c.sexousu), '') = ''
                        THEN NULLIF(TRIM(s.sexousu), '')
                        ELSE c.sexousu END AS sexo_novo,
                   c.cpfusu AS cpf_atual,
                   CASE WHEN COALESCE(TRIM(c.cpfusu), '') = ''
                        THEN NULLIF(TRIM(s.cpfusu), '')
                        ELSE c.cpfusu END AS cpf_novo,
                   c.cns AS cns_atual,
                   CASE WHEN COALESCE(TRIM(c.cns), '') = ''
                        THEN NULLIF(TRIM(s.cns), '')
                        ELSE c.cns END AS cns_novo,
                   c.codcco AS codcco_atual,
                   CASE WHEN COALESCE(TRIM(c.codcco), '') = ''
                        THEN NULLIF(TRIM(s.codcco), '')
                        ELSE c.codcco END AS codcco_novo,
                   c.posans AS posans_atual,
                   CASE
                     WHEN COALESCE(
                            NULLIF(TRIM(
                              CASE WHEN COALESCE(TRIM(c.nomeusu), '') = ''
                                   THEN s.nomeusu ELSE c.nomeusu END
                            ), ''),
                            ''
                          ) <> ''
                      AND COALESCE(c.nascusu, {NASC_CONFSIB}) IS NOT NULL
                      AND COALESCE(
                            NULLIF(TRIM(
                              CASE WHEN COALESCE(TRIM(c.sexousu), '') = ''
                                   THEN s.sexousu ELSE c.sexousu END
                            ), ''),
                            ''
                          ) <> ''
                      AND (
                            COALESCE(NULLIF(TRIM(
                              CASE WHEN COALESCE(TRIM(c.cpfusu), '') = ''
                                   THEN s.cpfusu ELSE c.cpfusu END
                            ), ''), '') <> ''
                         OR COALESCE(NULLIF(TRIM(
                              CASE WHEN COALESCE(TRIM(c.cns), '') = ''
                                   THEN s.cns ELSE c.cns END
                            ), ''), '') <> ''
                      )
                     THEN CASE
                            WHEN COALESCE(NULLIF(TRIM(
                                   CASE WHEN COALESCE(TRIM(c.codcco), '') = ''
                                        THEN s.codcco ELSE c.codcco END
                                 ), ''), '') <> ''
                            THEN '4-ATUALIZADO'
                            ELSE '1-INCLUSAO'
                          END
                     ELSE c.posans
                   END AS posans_novo,
                   c.dataini, s.dataini AS dataini_ans
            FROM cadusu c
            {CONFSIB_LATERAL_IDENTIDADE}
            WHERE {ATIVO_SIB_CAMPOS_AUSENTES}
              AND ({CONFSIB_PODE_PREENCHER_SIB})
            ORDER BY c.id
            {_limit()}
        """,
        apply_sql=f"""
            UPDATE cadusu c SET
                nomeusu = CASE
                    WHEN COALESCE(TRIM(c.nomeusu), '') = ''
                         AND COALESCE(TRIM(s.nomeusu), '') <> ''
                    THEN TRIM(s.nomeusu)
                    ELSE c.nomeusu
                END,
                nascusu = COALESCE(c.nascusu, {NASC_CONFSIB}),
                sexousu = CASE
                    WHEN COALESCE(TRIM(c.sexousu), '') = ''
                         AND COALESCE(TRIM(s.sexousu), '') <> ''
                    THEN TRIM(s.sexousu)
                    ELSE c.sexousu
                END,
                cpfusu = CASE
                    WHEN COALESCE(TRIM(c.cpfusu), '') = ''
                         AND COALESCE(TRIM(s.cpfusu), '') <> ''
                    THEN TRIM(s.cpfusu)
                    ELSE c.cpfusu
                END,
                cns = CASE
                    WHEN COALESCE(TRIM(c.cns), '') = ''
                         AND COALESCE(TRIM(s.cns), '') <> ''
                    THEN TRIM(s.cns)
                    ELSE c.cns
                END,
                codcco = CASE
                    WHEN COALESCE(TRIM(c.codcco), '') = ''
                         AND COALESCE(TRIM(s.codcco), '') <> ''
                    THEN TRIM(s.codcco)
                    ELSE c.codcco
                END,
                posans = CASE
                    WHEN COALESCE(
                           NULLIF(TRIM(
                             CASE WHEN COALESCE(TRIM(c.nomeusu), '') = ''
                                       AND COALESCE(TRIM(s.nomeusu), '') <> ''
                                  THEN TRIM(s.nomeusu) ELSE c.nomeusu END
                           ), ''),
                           ''
                         ) <> ''
                     AND COALESCE(c.nascusu, {NASC_CONFSIB}) IS NOT NULL
                     AND COALESCE(
                           NULLIF(TRIM(
                             CASE WHEN COALESCE(TRIM(c.sexousu), '') = ''
                                       AND COALESCE(TRIM(s.sexousu), '') <> ''
                                  THEN TRIM(s.sexousu) ELSE c.sexousu END
                           ), ''),
                           ''
                         ) <> ''
                     AND (
                           COALESCE(NULLIF(TRIM(
                             CASE WHEN COALESCE(TRIM(c.cpfusu), '') = ''
                                       AND COALESCE(TRIM(s.cpfusu), '') <> ''
                                  THEN TRIM(s.cpfusu) ELSE c.cpfusu END
                           ), ''), '') <> ''
                        OR COALESCE(NULLIF(TRIM(
                             CASE WHEN COALESCE(TRIM(c.cns), '') = ''
                                       AND COALESCE(TRIM(s.cns), '') <> ''
                                  THEN TRIM(s.cns) ELSE c.cns END
                           ), ''), '') <> ''
                     )
                    THEN CASE
                           WHEN COALESCE(NULLIF(TRIM(
                                  CASE WHEN COALESCE(TRIM(c.codcco), '') = ''
                                            AND COALESCE(TRIM(s.codcco), '') <> ''
                                       THEN TRIM(s.codcco) ELSE c.codcco END
                                ), ''), '') <> ''
                           THEN '4-ATUALIZADO'
                           ELSE '1-INCLUSAO'
                         END
                    ELSE c.posans
                END,
                {_AUDIT}
            FROM confsib s
            WHERE c.id = ANY(%s)
              AND {ATIVO_SIB_CAMPOS_AUSENTES}
              AND s.numseq = (
                    SELECT MAX(s2.numseq)
                    FROM confsib s2
                    WHERE COALESCE(TRIM(c.nomeusu), '') <> ''
                      AND COALESCE(TRIM(s2.nomeusu), '') <> ''
                      AND UPPER(TRIM(c.nomeusu)) = UPPER(TRIM(s2.nomeusu))
                      AND c.nascusu IS NOT NULL
                      AND (
                            CASE
                              WHEN NULLIF(TRIM(s2.nascusu), '') IS NULL THEN NULL
                              WHEN TRIM(s2.nascusu) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$'
                                THEN TRIM(s2.nascusu)::date
                              WHEN TRIM(s2.nascusu) ~ '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}$'
                                THEN to_date(TRIM(s2.nascusu), 'DD/MM/YYYY')
                              ELSE NULL
                            END
                          ) = c.nascusu
                      AND c.dataini IS NOT NULL
                      AND (
                            CASE
                              WHEN NULLIF(TRIM(s2.dataini), '') IS NULL THEN NULL
                              WHEN TRIM(s2.dataini) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$'
                                THEN TRIM(s2.dataini)::date
                              WHEN TRIM(s2.dataini) ~ '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}$'
                                THEN to_date(TRIM(s2.dataini), 'DD/MM/YYYY')
                              ELSE NULL
                            END
                          ) = c.dataini
                      AND REGEXP_REPLACE(COALESCE(c.cpfusu, ''), '[^0-9]', '', 'g')
                        = REGEXP_REPLACE(COALESCE(s2.cpfusu, ''), '[^0-9]', '', 'g')
              )
              AND ({CONFSIB_PODE_PREENCHER_SIB})
            RETURNING c.id, c.codtit, c.codusu, c.nomeusu, c.nascusu, c.sexousu,
                      c.cpfusu, c.cns, c.codcco, c.posans
        """,
        count_sql=f"""
            SELECT COUNT(*) AS total
            FROM cadusu c
            {CONFSIB_LATERAL_IDENTIDADE}
            WHERE {ATIVO_SIB_CAMPOS_AUSENTES}
              AND ({CONFSIB_PODE_PREENCHER_SIB})
        """,
    ),
}


MANUAL_ONLY: dict[str, str] = {
    "exclusao_sem_datafim": (
        "INATIVO com 3-EXCLUSAO sem DATAFIM: preencher datafim manualmente "
        "(data de cancelamento do vínculo). Sem UPDATE automático."
    ),
    "cadusu_ausente_confsib": (
        "Exige análise operacional (envio SIB / competência do arquivo confsib). "
        "Não há UPDATE automático seguro."
    ),
    "confsib_sem_cadusu": (
        "Registro apenas na confsib — correção não é UPDATE em cadusu "
        "(avaliar reinclusão cadastral ou descarte do retorno)."
    ),
    "cco_duplicado": (
        "Duplicidade de CCO exige decisão cadastral (qual vínculo manter). Sem UPDATE em massa."
    ),
    "posans_desconhecido": (
        "POSANS fora do domínio precisa mapeamento manual antes de qualquer ajuste."
    ),
    "cpf_duplicado_ativos": (
        "CPF duplicado na mesma empresa exige análise cadastral "
        "(qual vínculo manter / corrigir). Sem UPDATE em massa."
    ),
    "cpf_duplicado_ativos_nasc_divergente": (
        "Mesmo CPF com nascimentos diferentes na mesma empresa: "
        "use a regra 'CPF inválido para a data de nascimento' para limpar "
        "o CPF dos cadastros inconsistentes."
    ),
}


def get_fix_plan(rule_id: str) -> FixPlan | None:
    return FIX_PLANS.get(rule_id)


def fix_meta(rule_id: str) -> dict[str, Any]:
    plan = get_fix_plan(rule_id)
    if plan:
        return {
            "fixable": True,
            "fix_label": plan.label,
            "fix_summary": plan.summary,
            "fix_fields": list(plan.fields),
            "manual_reason": None,
        }
    return {
        "fixable": False,
        "fix_label": None,
        "fix_summary": None,
        "fix_fields": [],
        "manual_reason": MANUAL_ONLY.get(
            rule_id,
            "Esta regra não possui correção automática cadastrada.",
        ),
    }


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def preview_fix(rule_id: str, ids: list[int] | None = None) -> dict[str, Any]:
    plan = get_fix_plan(rule_id)
    if not plan:
        meta = fix_meta(rule_id)
        raise ValueError(meta["manual_reason"] or "Correção automática indisponível.")

    rows = fetch_all(plan.preview_sql)
    if ids:
        id_set = set(int(i) for i in ids)
        rows = [r for r in rows if int(r["id"]) in id_set]

    total_eligible = fetch_count(plan.count_sql)
    return {
        "rule_id": rule_id,
        "fixable": True,
        "label": plan.label,
        "summary": plan.summary,
        "fields": list(plan.fields),
        "total_eligible": total_eligible,
        "returned": len(rows),
        "truncated": total_eligible > len(rows),
        "max_rows": Config.MAX_ROWS,
        "columns": list(rows[0].keys()) if rows else [],
        "rows": [_serialize(r) for r in rows],
    }


def apply_fix(rule_id: str, ids: list[int], confirm: bool = False) -> dict[str, Any]:
    if not confirm:
        raise ValueError("Confirmação obrigatória (confirm=true) para gravar alterações.")
    if not ids:
        raise ValueError("Nenhum id informado para correção.")

    plan = get_fix_plan(rule_id)
    if not plan:
        meta = fix_meta(rule_id)
        raise ValueError(meta["manual_reason"] or "Correção automática indisponível.")

    clean_ids = sorted({int(i) for i in ids})
    if len(clean_ids) > Config.MAX_ROWS:
        raise ValueError(f"Limite de {Config.MAX_ROWS} registros por gravação.")

    updated = execute_returning(plan.apply_sql, (clean_ids,))
    return {
        "rule_id": rule_id,
        "requested": len(clean_ids),
        "updated": len(updated),
        "label": plan.label,
        "rows": [_serialize(r) for r in updated],
    }
