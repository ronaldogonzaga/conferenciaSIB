from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from config import Config
from db import fetch_all, fetch_count


CADUSU_COLS = """
    id, codtit, codusu, nomeusu, situusu, posans, codcco, codans,
    cpfusu, nascusu, sexousu, dataini, datafim, dataexc, datareinc,
    dataalt, mae, cns, codplano, codplaport, parentesco, datacad
"""


NASC_CONFSIB = """
CASE
  WHEN NULLIF(TRIM(s.nascusu), '') IS NULL THEN NULL
  WHEN TRIM(s.nascusu) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
    THEN TRIM(s.nascusu)::date
  WHEN TRIM(s.nascusu) ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}$'
    THEN to_date(TRIM(s.nascusu), 'DD/MM/YYYY')
  ELSE NULL
END
"""


NASC_IGUAL = f"(c.nascusu IS NOT NULL AND ({NASC_CONFSIB}) = c.nascusu)"


DATAINI_CONFSIB = """
CASE
  WHEN NULLIF(TRIM(s.dataini), '') IS NULL THEN NULL
  WHEN TRIM(s.dataini) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
    THEN TRIM(s.dataini)::date
  WHEN TRIM(s.dataini) ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}$'
    THEN to_date(TRIM(s.dataini), 'DD/MM/YYYY')
  ELSE NULL
END
"""

# RN 500/2022: movimentação do mês M deve ir até o dia 5 de M+1.
# True quando o prazo de envio da dataini já venceu (a partir do dia 6 de M+1).
# Sem dataini: considera vencido (não há competência para proteger).
PRAZO_ENVIO_DATAINI_VENCIDO = """
(
  dataini IS NULL
  OR CURRENT_DATE > (
    (date_trunc('month', dataini) + INTERVAL '1 month')::date + 4
  )
)
"""


DATAFIM_CONFSIB = """
CASE
  WHEN NULLIF(TRIM(s.datafim), '') IS NULL THEN NULL
  WHEN TRIM(s.datafim) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
    THEN TRIM(s.datafim)::date
  WHEN TRIM(s.datafim) ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}$'
    THEN to_date(TRIM(s.datafim), 'DD/MM/YYYY')
  ELSE NULL
END
"""


PLANO_CONFSIB = """
COALESCE(NULLIF(TRIM(s.codplaport), ''), NULLIF(TRIM(s.codplaope), ''), '')
"""


CONFSIB_LATERAL = """
INNER JOIN LATERAL (
    SELECT s0.*
    FROM confsib s0
    WHERE s0.codcco = c.codcco
    ORDER BY s0.numseq DESC
    LIMIT 1
) s ON TRUE
"""


MATCH_CONFSIB_IDENTIDADE = f"""
    COALESCE(TRIM(c.nomeusu), '') <> ''
    AND COALESCE(TRIM(s.nomeusu), '') <> ''
    AND UPPER(TRIM(c.nomeusu)) = UPPER(TRIM(s.nomeusu))
    AND c.nascusu IS NOT NULL
    AND ({NASC_CONFSIB}) IS NOT NULL
    AND ({NASC_CONFSIB}) = c.nascusu
    AND c.dataini IS NOT NULL
    AND ({DATAINI_CONFSIB}) IS NOT NULL
    AND ({DATAINI_CONFSIB}) = c.dataini
    AND REGEXP_REPLACE(COALESCE(c.cpfusu, ''), '[^0-9]', '', 'g')
      = REGEXP_REPLACE(COALESCE(s.cpfusu, ''), '[^0-9]', '', 'g')
"""

CONFSIB_LATERAL_IDENTIDADE = f"""
INNER JOIN LATERAL (
    SELECT s0.*
    FROM confsib s0
    WHERE COALESCE(TRIM(c.nomeusu), '') <> ''
      AND COALESCE(TRIM(s0.nomeusu), '') <> ''
      AND UPPER(TRIM(c.nomeusu)) = UPPER(TRIM(s0.nomeusu))
      AND c.nascusu IS NOT NULL
      AND (
            CASE
              WHEN NULLIF(TRIM(s0.nascusu), '') IS NULL THEN NULL
              WHEN TRIM(s0.nascusu) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$'
                THEN TRIM(s0.nascusu)::date
              WHEN TRIM(s0.nascusu) ~ '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}$'
                THEN to_date(TRIM(s0.nascusu), 'DD/MM/YYYY')
              ELSE NULL
            END
          ) = c.nascusu
      AND c.dataini IS NOT NULL
      AND (
            CASE
              WHEN NULLIF(TRIM(s0.dataini), '') IS NULL THEN NULL
              WHEN TRIM(s0.dataini) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$'
                THEN TRIM(s0.dataini)::date
              WHEN TRIM(s0.dataini) ~ '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}$'
                THEN to_date(TRIM(s0.dataini), 'DD/MM/YYYY')
              ELSE NULL
            END
          ) = c.dataini
      AND REGEXP_REPLACE(COALESCE(c.cpfusu, ''), '[^0-9]', '', 'g')
        = REGEXP_REPLACE(COALESCE(s0.cpfusu, ''), '[^0-9]', '', 'g')
    ORDER BY s0.numseq DESC
    LIMIT 1
) s ON TRUE
"""


ATIVO_SIB_CAMPOS_AUSENTES = """
    c.situusu = 'ATIVO'
    AND (
           COALESCE(TRIM(c.nomeusu), '') = ''
        OR c.nascusu IS NULL
        OR COALESCE(TRIM(c.sexousu), '') = ''
        OR (
              COALESCE(TRIM(c.cpfusu), '') = ''
          AND COALESCE(TRIM(c.cns), '') = ''
        )
    )
"""


CONFSIB_PODE_PREENCHER_SIB = f"""
    (
         (COALESCE(TRIM(c.nomeusu), '') = '' AND COALESCE(TRIM(s.nomeusu), '') <> '')
      OR (c.nascusu IS NULL AND ({NASC_CONFSIB}) IS NOT NULL)
      OR (COALESCE(TRIM(c.sexousu), '') = '' AND COALESCE(TRIM(s.sexousu), '') <> '')
      OR (COALESCE(TRIM(c.cpfusu), '') = '' AND COALESCE(TRIM(s.cpfusu), '') <> '')
      OR (COALESCE(TRIM(c.cns), '') = '' AND COALESCE(TRIM(s.cns), '') <> '')
      OR (COALESCE(TRIM(c.codcco), '') = '' AND COALESCE(TRIM(s.codcco), '') <> '')
    )
"""


DIFF_ANSRG = """
UPPER(REGEXP_REPLACE(COALESCE(c.rgusu, ''), '[^0-9A-Za-z]', '', 'g'))
  <> UPPER(REGEXP_REPLACE(COALESCE(s.docident, ''), '[^0-9A-Za-z]', '', 'g'))
"""
DIFF_ANSCPF = """
REGEXP_REPLACE(COALESCE(c.cpfusu, ''), '[^0-9]', '', 'g')
  <> REGEXP_REPLACE(COALESCE(s.cpfusu, ''), '[^0-9]', '', 'g')
"""
DIFF_ANSMAE = """
UPPER(TRIM(COALESCE(c.mae, ''))) <> UPPER(TRIM(COALESCE(s.mae, '')))
"""
DIFF_ANSCNS = """
REGEXP_REPLACE(COALESCE(c.cns, ''), '[^0-9]', '', 'g')
  <> REGEXP_REPLACE(COALESCE(s.cns, ''), '[^0-9]', '', 'g')
"""
DIFF_ANSNASC = f"c.nascusu IS DISTINCT FROM ({NASC_CONFSIB})"
DIFF_ANSPARENTESCO = """
UPPER(TRIM(COALESCE(c.parentesco, '')))
  <> UPPER(TRIM(COALESCE(s.parentesco, '')))
"""
DIFF_ANSNOME = """
UPPER(TRIM(COALESCE(c.nomeusu, '')))
  <> UPPER(TRIM(COALESCE(s.nomeusu, '')))
"""
DIFF_ANSPLANO = f"""
UPPER(TRIM(COALESCE(c.codplano, '')))
  <> UPPER(TRIM({PLANO_CONFSIB}))
"""
DIFF_ANSDATAINI = f"c.dataini IS DISTINCT FROM ({DATAINI_CONFSIB})"
DIFF_ANSDATAFIM = f"c.datafim IS DISTINCT FROM ({DATAFIM_CONFSIB})"

SIB_FLEX_DIFFS = (
    ("ansrg", DIFF_ANSRG),
    ("anscpf", DIFF_ANSCPF),
    ("ansmae", DIFF_ANSMAE),
    ("anscns", DIFF_ANSCNS),
    ("ansnasc", DIFF_ANSNASC),
    ("ansparentesco", DIFF_ANSPARENTESCO),
    ("ansnome", DIFF_ANSNOME),
    ("ansplano", DIFF_ANSPLANO),
    ("ansdataini", DIFF_ANSDATAINI),
    ("ansdatafim", DIFF_ANSDATAFIM),
)
SIB_FLEX_ALGUM_DIFF = " OR ".join(f"({d})" for _, d in SIB_FLEX_DIFFS)
SIB_FLEX_FLAG_CASE = ",\n                ".join(
    f"{flag} = CASE WHEN ({diff}) THEN '1' ELSE c.{flag} END"
    for flag, diff in SIB_FLEX_DIFFS
)
SIB_FLEX_PREVIEW_FLAGS = ",\n                   ".join(
    f"c.{flag} AS {flag}_atual,\n                   "
    f"CASE WHEN ({diff}) THEN '1' ELSE c.{flag} END AS {flag}_novo"
    for flag, diff in SIB_FLEX_DIFFS
)


MESMO_REGISTRO_CONFSIB = f"""
    COALESCE(c.codcco, '') <> ''
    AND s.codcco = c.codcco
    AND c.dataini IS NOT NULL
    AND ({DATAINI_CONFSIB}) = c.dataini
    AND COALESCE(TRIM(c.cpfusu), '') <> ''
    AND TRIM(s.cpfusu) = TRIM(c.cpfusu)
    AND COALESCE(TRIM(c.nomeusu), '') <> ''
    AND UPPER(TRIM(COALESCE(s.nomeusu, ''))) = UPPER(TRIM(c.nomeusu))
"""


# Mesmo beneficiário (campos-chave preenchidos e iguais nos dois lados).
MESMO_REGISTRO_EXATO = f"""
    COALESCE(TRIM(c.codcco), '') <> ''
    AND TRIM(s.codcco) = TRIM(c.codcco)
    AND COALESCE(TRIM(c.nomeusu), '') <> ''
    AND COALESCE(TRIM(s.nomeusu), '') <> ''
    AND UPPER(TRIM(c.nomeusu)) = UPPER(TRIM(s.nomeusu))
    AND COALESCE(TRIM(c.cpfusu), '') <> ''
    AND COALESCE(TRIM(s.cpfusu), '') <> ''
    AND TRIM(c.cpfusu) = TRIM(s.cpfusu)
    AND c.nascusu IS NOT NULL
    AND ({NASC_CONFSIB}) IS NOT NULL
    AND ({NASC_CONFSIB}) = c.nascusu
    AND c.dataini IS NOT NULL
    AND ({DATAINI_CONFSIB}) IS NOT NULL
    AND ({DATAINI_CONFSIB}) = c.dataini
"""


# Quando o CCO casa, exige que CPF / nascimento / nome não contradigam
# (campos preenchidos nos dois lados devem coincidir).
COMPAT_CHAVES_CONFSIB = f"""
    (
        COALESCE(TRIM(c.cpfusu), '') = ''
        OR COALESCE(TRIM(s.cpfusu), '') = ''
        OR TRIM(c.cpfusu) = TRIM(s.cpfusu)
    )
    AND (
        c.nascusu IS NULL
        OR ({NASC_CONFSIB}) IS NULL
        OR ({NASC_CONFSIB}) = c.nascusu
    )
    AND (
        COALESCE(TRIM(c.nomeusu), '') = ''
        OR COALESCE(TRIM(s.nomeusu), '') = ''
        OR UPPER(TRIM(c.nomeusu)) = UPPER(TRIM(s.nomeusu))
    )
"""


# Último registro confsib por CCO (numseq mais recente).
CONFSIB_LATEST_BY_CCO = """
    SELECT DISTINCT ON (s0.codcco) s0.*
    FROM confsib s0
    WHERE COALESCE(TRIM(s0.codcco), '') <> ''
    ORDER BY s0.codcco, s0.numseq DESC
"""


def ids_sql_divergencia_situacao(
    situusu: str,
    status_ans: str,
    extra_cadusu_where: str = "",
) -> str:
    """IDs cadusu com divergência de situação vs confsib (chaves da conferência)."""
    extra = f"\n                  {extra_cadusu_where}" if extra_cadusu_where else ""
    return f"""
                SELECT c.id
                FROM cadusu c
                INNER JOIN (
                    {CONFSIB_LATEST_BY_CCO}
                ) s ON s.codcco = c.codcco
                WHERE c.situusu = '{situusu}'
                  AND TRIM(s.status) = '{status_ans}'
                  AND {COMPAT_CHAVES_CONFSIB}{extra}

                UNION

                SELECT c.id
                FROM cadusu c
                WHERE c.situusu = '{situusu}'
                  AND COALESCE(TRIM(c.codcco), '') = ''
                  AND COALESCE(TRIM(c.codans), '') <> ''{extra}
                  AND EXISTS (
                      SELECT 1 FROM confsib s
                      WHERE s.codusu = c.codans
                        AND {NASC_IGUAL}
                        AND TRIM(s.status) = '{status_ans}'
                  )

                UNION

                SELECT c.id
                FROM cadusu c
                WHERE c.situusu = '{situusu}'
                  AND COALESCE(TRIM(c.codcco), '') = ''
                  AND COALESCE(TRIM(c.cpfusu), '') <> ''{extra}
                  AND EXISTS (
                      SELECT 1 FROM confsib s
                      WHERE s.cpfusu = c.cpfusu
                        AND {NASC_IGUAL}
                        AND TRIM(s.status) = '{status_ans}'
                  )
    """


def _sql_divergencia_situacao(
    situusu: str,
    status_ans: str,
    extra_cadusu_where: str = "",
) -> tuple[str, str]:
    """cadusu.situusu vs confsib.status (A=ativo, I=inativo), mesmas chaves da conferência."""
    extra = f"\n                  {extra_cadusu_where}" if extra_cadusu_where else ""
    ids_sql = ids_sql_divergencia_situacao(situusu, status_ans, extra_cadusu_where)
    count_sql = f"""
            SELECT COUNT(*) AS total FROM (
                {ids_sql}
            ) q
        """
    detail_sql = f"""
            SELECT * FROM (
                SELECT c.id, c.codtit, c.codusu, c.nomeusu, c.situusu, c.posans,
                       c.codcco, c.codans, c.cpfusu, c.nascusu, c.dataini, c.datafim,
                       s.status AS status_ans, s.codcco AS cco_ans, s.codusu AS codusu_ans,
                       s.nomeusu AS nome_ans, s.cpfusu AS cpf_ans, s.nascusu AS nasc_ans,
                       s.dataini AS dataini_ans, s.datafim AS datafim_ans,
                       'CODCCO (+ compat. CPF/nome/nasc)'::text AS chave_usada
                FROM cadusu c
                INNER JOIN (
                    {CONFSIB_LATEST_BY_CCO}
                ) s ON s.codcco = c.codcco
                WHERE c.situusu = '{situusu}'
                  AND TRIM(s.status) = '{status_ans}'
                  AND {COMPAT_CHAVES_CONFSIB}{extra}

                UNION ALL

                SELECT c.id, c.codtit, c.codusu, c.nomeusu, c.situusu, c.posans,
                       c.codcco, c.codans, c.cpfusu, c.nascusu, c.dataini, c.datafim,
                       s.status AS status_ans, s.codcco AS cco_ans, s.codusu AS codusu_ans,
                       s.nomeusu AS nome_ans, s.cpfusu AS cpf_ans, s.nascusu AS nasc_ans,
                       s.dataini AS dataini_ans, s.datafim AS datafim_ans,
                       CASE
                         WHEN COALESCE(TRIM(c.codans), '') <> ''
                              AND s.codusu = c.codans THEN 'CODANS=CODUSU + nascimento'
                         ELSE 'CPF + nascimento'
                       END AS chave_usada
                FROM cadusu c
                INNER JOIN LATERAL (
                    SELECT s0.*
                    FROM confsib s0
                    WHERE COALESCE(TRIM(c.codcco), '') = ''
                      AND TRIM(s0.status) = '{status_ans}'
                      AND (
                          (
                              COALESCE(TRIM(c.codans), '') <> ''
                              AND s0.codusu = c.codans
                              AND c.nascusu IS NOT NULL
                              AND (
                                  CASE
                                    WHEN NULLIF(TRIM(s0.nascusu), '') IS NULL THEN NULL
                                    WHEN TRIM(s0.nascusu) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$'
                                      THEN TRIM(s0.nascusu)::date
                                    WHEN TRIM(s0.nascusu) ~ '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}$'
                                      THEN to_date(TRIM(s0.nascusu), 'DD/MM/YYYY')
                                    ELSE NULL
                                  END
                              ) = c.nascusu
                          )
                          OR (
                              COALESCE(TRIM(c.cpfusu), '') <> ''
                              AND s0.cpfusu = c.cpfusu
                              AND c.nascusu IS NOT NULL
                              AND (
                                  CASE
                                    WHEN NULLIF(TRIM(s0.nascusu), '') IS NULL THEN NULL
                                    WHEN TRIM(s0.nascusu) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$'
                                      THEN TRIM(s0.nascusu)::date
                                    WHEN TRIM(s0.nascusu) ~ '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}$'
                                      THEN to_date(TRIM(s0.nascusu), 'DD/MM/YYYY')
                                    ELSE NULL
                                  END
                              ) = c.nascusu
                          )
                      )
                    ORDER BY s0.numseq DESC
                    LIMIT 1
                ) s ON TRUE
                WHERE c.situusu = '{situusu}'
                  AND COALESCE(TRIM(c.codcco), '') = ''{extra}
            ) q
            ORDER BY q.chave_usada, q.codtit, q.codusu
            {_limit_clause()}
        """
    return count_sql, detail_sql


# Já em 8-REINCLUSAO: pendente de sincronização ANS (confsib pode demorar 30+ dias).
_EXTRA_SEM_REINCLUSAO_PENDENTE = "AND c.posans <> '8-REINCLUSAO'"

# Elegível à correção 8-REINCLUSAO: CCO + campos obrigatórios SIB/ANS preenchidos.
CAMPOS_OBRIGATORIOS_ANS_OK = """
    COALESCE(TRIM(c.codcco), '') <> ''
    AND COALESCE(TRIM(c.nomeusu), '') <> ''
    AND c.nascusu IS NOT NULL
    AND COALESCE(TRIM(c.sexousu), '') <> ''
    AND (
           COALESCE(TRIM(c.cpfusu), '') <> ''
        OR COALESCE(TRIM(c.cns), '') <> ''
    )
"""

EXTRA_FIX_REINCLUSAO = f"""
    AND c.posans <> '8-REINCLUSAO'
    AND COALESCE(TRIM(c.codcco), '') <> ''
    AND ({CAMPOS_OBRIGATORIOS_ANS_OK})
"""


def ids_sql_fix_ativo_inativo_confsib() -> str:
    """
    IDs elegíveis ao UPDATE 8-REINCLUSAO.

    Exige CCO preenchido na cadusu, mesmo registro na confsib
    (CCO + nome + CPF + nascimento + dataini) e campos obrigatórios ANS.
    Sem CCO na cadusu: nao atualiza.
    """
    from pending_confsib import sql_exclude_pending

    excl = sql_exclude_pending("ativo_inativo_confsib_reinclusao")
    return f"""
                SELECT c.id
                FROM cadusu c
                INNER JOIN (
                    {CONFSIB_LATEST_BY_CCO}
                ) s ON TRIM(s.codcco) = TRIM(c.codcco)
                WHERE c.situusu = 'ATIVO'
                  AND TRIM(s.status) = 'I'
                  AND COALESCE(TRIM(c.codcco), '') <> ''
                  AND {MESMO_REGISTRO_EXATO}
                  {EXTRA_FIX_REINCLUSAO}
                  {EXTRA_SEM_VALIDACAO_COMPLETA_PARA_4}
                  {excl}
    """


def _sql_ativo_inativo_mesmo_registro() -> tuple[str, str]:
    """ATIVO cadusu + INATIVO confsib com identidade exata
    (CCO+nome+CPF+nasc+dataini).

    Exige CCO na cadusu. Já corrigidos (8-REINCLUSAO) ou no controle SQLite
    de aguardo confsib nao entram na listagem.
    """
    from pending_confsib import sql_exclude_pending

    excl_pending = sql_exclude_pending("ativo_inativo_confsib_reinclusao")
    count_sql = f"""
            SELECT COUNT(*) AS total
            FROM cadusu c
            INNER JOIN (
                {CONFSIB_LATEST_BY_CCO}
            ) s ON TRIM(s.codcco) = TRIM(c.codcco)
            WHERE c.situusu = 'ATIVO'
              AND TRIM(s.status) = 'I'
              AND COALESCE(TRIM(c.codcco), '') <> ''
              AND c.posans <> '8-REINCLUSAO'
              AND {MESMO_REGISTRO_EXATO}
              AND ({CAMPOS_OBRIGATORIOS_ANS_OK})
              {EXTRA_SEM_VALIDACAO_COMPLETA_PARA_4}
              {excl_pending}
        """
    detail_sql = f"""
            SELECT c.id, c.codtit, c.codusu, c.nomeusu, c.situusu, c.posans,
                   c.codcco, c.codans, c.cpfusu, c.cns, c.sexousu,
                   c.nascusu, c.dataini, c.datafim,
                   s.status AS status_ans, s.codcco AS cco_ans, s.codusu AS codusu_ans,
                   s.nomeusu AS nome_ans, s.cpfusu AS cpf_ans, s.nascusu AS nasc_ans,
                   s.dataini AS dataini_ans, s.datafim AS datafim_ans,
                   'CCO + nome + CPF + nascimento + dataini'::text AS chave_usada,
                   'pendente de reinclusao'::text AS situacao_correcao
            FROM cadusu c
            INNER JOIN (
                {CONFSIB_LATEST_BY_CCO}
            ) s ON TRIM(s.codcco) = TRIM(c.codcco)
            WHERE c.situusu = 'ATIVO'
              AND TRIM(s.status) = 'I'
              AND COALESCE(TRIM(c.codcco), '') <> ''
              AND c.posans <> '8-REINCLUSAO'
              AND {MESMO_REGISTRO_EXATO}
              AND ({CAMPOS_OBRIGATORIOS_ANS_OK})
              {EXTRA_SEM_VALIDACAO_COMPLETA_PARA_4}
              {excl_pending}
            ORDER BY
              c.dataini DESC NULLS LAST,
              c.codtit, c.codusu
            {_limit_clause()}
        """
    return count_sql, detail_sql


# Exclui da regra geral os casos cobertos pela reinclusão (mesmo registro).
EXTRA_SEM_MESMO_REGISTRO_REINCLUSAO = f"""
    AND NOT EXISTS (
        SELECT 1
        FROM (
            {CONFSIB_LATEST_BY_CCO}
        ) s
        WHERE s.codcco = c.codcco
          AND TRIM(s.status) = 'I'
          AND {MESMO_REGISTRO_EXATO}
          AND ({CAMPOS_OBRIGATORIOS_ANS_OK})
    )
"""


# Já em 3-EXCLUSAO: pendente de baixa na ANS (confsib pode demorar 30+ dias).
_EXTRA_SEM_EXCLUSAO_PENDENTE = "AND c.posans <> '3-EXCLUSAO'"

EXTRA_FIX_EXCLUSAO = f"""
    AND c.posans <> '3-EXCLUSAO'
    AND c.datafim IS NOT NULL
    AND COALESCE(TRIM(c.codcco), '') <> ''
"""

# codusu local ou codans (código ANS) igual ao codusu da confsib.
CODUSU_IGUAL_CONFSIB = """
(
    UPPER(TRIM(COALESCE(c.codusu, ''))) = UPPER(TRIM(COALESCE(s.codusu, '')))
    OR (
        COALESCE(TRIM(c.codans), '') <> ''
        AND UPPER(TRIM(c.codans)) = UPPER(TRIM(COALESCE(s.codusu, '')))
    )
)
"""

DATAINI_IGUAL_CONFSIB = f"""
(
    c.dataini IS NOT NULL
    AND ({DATAINI_CONFSIB}) IS NOT NULL
    AND ({DATAINI_CONFSIB}) = c.dataini
)
"""

# Mesma pessoa: nome + CPF + nascimento + dataini + codusu/codans.
IDENTIDADE_VALIDACAO_COMPLETA = f"""
(
    COALESCE(TRIM(c.nomeusu), '') <> ''
    AND COALESCE(TRIM(s.nomeusu), '') <> ''
    AND UPPER(TRIM(c.nomeusu)) = UPPER(TRIM(s.nomeusu))
    AND LENGTH(REGEXP_REPLACE(COALESCE(c.cpfusu, ''), '[^0-9]', '', 'g')) = 11
    AND REGEXP_REPLACE(COALESCE(c.cpfusu, ''), '[^0-9]', '', 'g')
      = REGEXP_REPLACE(COALESCE(s.cpfusu, ''), '[^0-9]', '', 'g')
    AND {NASC_IGUAL}
    AND {DATAINI_IGUAL_CONFSIB}
    AND {CODUSU_IGUAL_CONFSIB}
)
"""

# Reinclusão (8) nao compete com conciliacao local (4) quando validacao completa.
EXTRA_SEM_VALIDACAO_COMPLETA_PARA_4 = f"""
    AND NOT {IDENTIDADE_VALIDACAO_COMPLETA}
"""


def ids_sql_fix_ativo_cadusu_inativo_confsib() -> str:
    """
    ATIVO cadusu + INATIVO confsib com identidade de validacao completa.
    Parte da cadusu (conjunto menor) e busca o ultimo confsib por CCO/CPF.
    """
    return f"""
                SELECT c.id
                FROM cadusu c
                INNER JOIN LATERAL (
                    SELECT s0.*
                    FROM confsib s0
                    WHERE TRIM(s0.codcco) = TRIM(c.codcco)
                    ORDER BY s0.numseq DESC
                    LIMIT 1
                ) s ON TRUE
                WHERE c.situusu = 'ATIVO'
                  AND COALESCE(TRIM(c.codcco), '') <> ''
                  AND c.posans <> '4-ATUALIZADO'
                  AND TRIM(s.status) = 'I'
                  AND {IDENTIDADE_VALIDACAO_COMPLETA}

                UNION

                SELECT c.id
                FROM cadusu c
                INNER JOIN LATERAL (
                    SELECT s0.*
                    FROM confsib s0
                    WHERE TRIM(COALESCE(s0.cpfusu, '')) = TRIM(COALESCE(c.cpfusu, ''))
                      AND TRIM(s0.status) = 'I'
                      AND COALESCE(TRIM(s0.codcco), '') <> ''
                    ORDER BY s0.numseq DESC
                    LIMIT 1
                ) s ON TRUE
                WHERE c.situusu = 'ATIVO'
                  AND c.posans = '1-INCLUSAO'
                  AND COALESCE(TRIM(c.codcco), '') = ''
                  AND LENGTH(REGEXP_REPLACE(COALESCE(c.cpfusu, ''), '[^0-9]', '', 'g')) = 11
                  AND {IDENTIDADE_VALIDACAO_COMPLETA}
    """


def _sql_ativo_cadusu_inativo_validacao_completa() -> tuple[str, str]:
    """ATIVO local + INATIVO ANS somente com todos os campos de validacao iguais."""
    count_sql = f"""
            SELECT COUNT(*) AS total FROM (
                {ids_sql_fix_ativo_cadusu_inativo_confsib()}
            ) q
        """
    detail_sql = f"""
            SELECT * FROM (
                (
                    SELECT c.id, c.codtit, c.codusu, c.nomeusu, c.situusu, c.posans,
                           c.codcco, c.codans, c.cpfusu, c.nascusu, c.dataini, c.datafim,
                           s.status AS status_ans, s.codcco AS cco_ans, s.codusu AS codusu_ans,
                           s.nomeusu AS nome_ans, s.cpfusu AS cpf_ans, s.nascusu AS nasc_ans,
                           s.dataini AS dataini_ans, s.datafim AS datafim_ans,
                           'validacao completa (CCO)'::text AS chave_usada,
                           'posans -> 4-ATUALIZADO'::text AS situacao_correcao
                    FROM cadusu c
                    INNER JOIN LATERAL (
                        SELECT s0.*
                        FROM confsib s0
                        WHERE TRIM(s0.codcco) = TRIM(c.codcco)
                        ORDER BY s0.numseq DESC
                        LIMIT 1
                    ) s ON TRUE
                    WHERE c.situusu = 'ATIVO'
                      AND COALESCE(TRIM(c.codcco), '') <> ''
                      AND c.posans <> '4-ATUALIZADO'
                      AND TRIM(s.status) = 'I'
                      AND {IDENTIDADE_VALIDACAO_COMPLETA}
                )
                UNION ALL
                (
                    SELECT c.id, c.codtit, c.codusu, c.nomeusu, c.situusu, c.posans,
                           c.codcco, c.codans, c.cpfusu, c.nascusu, c.dataini, c.datafim,
                           s.status AS status_ans, s.codcco AS cco_ans, s.codusu AS codusu_ans,
                           s.nomeusu AS nome_ans, s.cpfusu AS cpf_ans, s.nascusu AS nasc_ans,
                           s.dataini AS dataini_ans, s.datafim AS datafim_ans,
                           'validacao completa (sem CCO local)'::text AS chave_usada,
                           'vincular CCO + 4-ATUALIZADO'::text AS situacao_correcao
                    FROM cadusu c
                    INNER JOIN LATERAL (
                        SELECT s0.*
                        FROM confsib s0
                        WHERE TRIM(COALESCE(s0.cpfusu, '')) = TRIM(COALESCE(c.cpfusu, ''))
                          AND TRIM(s0.status) = 'I'
                          AND COALESCE(TRIM(s0.codcco), '') <> ''
                        ORDER BY s0.numseq DESC
                        LIMIT 1
                    ) s ON TRUE
                    WHERE c.situusu = 'ATIVO'
                      AND c.posans = '1-INCLUSAO'
                      AND COALESCE(TRIM(c.codcco), '') = ''
                      AND LENGTH(REGEXP_REPLACE(COALESCE(c.cpfusu, ''), '[^0-9]', '', 'g')) = 11
                      AND {IDENTIDADE_VALIDACAO_COMPLETA}
                )
            ) q
            ORDER BY q.dataini DESC NULLS LAST, q.posans, q.codtit, q.codusu
            {_limit_clause()}
        """
    return count_sql, detail_sql


def _sql_inativo_ativo_por_cco(extra_cadusu_where: str = "") -> tuple[str, str]:
    """INATIVO cadusu + ATIVO confsib, somente match por chave CCO (+ compat.)."""
    from pending_confsib import sql_exclude_pending

    extra = f"\n                  {extra_cadusu_where}" if extra_cadusu_where else ""
    excl_pending = sql_exclude_pending("inativo_cadusu_ativo_confsib")
    count_sql = f"""
            SELECT COUNT(*) AS total
            FROM cadusu c
            INNER JOIN (
                {CONFSIB_LATEST_BY_CCO}
            ) s ON s.codcco = c.codcco
            WHERE c.situusu = 'INATIVO'
              AND TRIM(s.status) = 'A'
              AND {COMPAT_CHAVES_CONFSIB}{extra}
              {excl_pending}
        """
    detail_sql = f"""
            SELECT c.id, c.codtit, c.codusu, c.nomeusu, c.situusu, c.posans,
                   c.codcco, c.codans, c.cpfusu, c.nascusu, c.dataini, c.datafim,
                   s.status AS status_ans, s.codcco AS cco_ans, s.codusu AS codusu_ans,
                   s.nomeusu AS nome_ans, s.cpfusu AS cpf_ans, s.nascusu AS nasc_ans,
                   s.dataini AS dataini_ans, s.datafim AS datafim_ans,
                   'CODCCO (+ compat. CPF/nome/nasc)'::text AS chave_usada
            FROM cadusu c
            INNER JOIN (
                {CONFSIB_LATEST_BY_CCO}
            ) s ON s.codcco = c.codcco
            WHERE c.situusu = 'INATIVO'
              AND TRIM(s.status) = 'A'
              AND {COMPAT_CHAVES_CONFSIB}{extra}
              {excl_pending}
            ORDER BY c.codtit, c.codusu
            {_limit_clause()}
        """
    return count_sql, detail_sql


def ids_sql_fix_inativo_ativo_confsib() -> str:
    """
    IDs elegíveis ao UPDATE 3-EXCLUSAO.

    Match por chave CCO (+ compat.) e datafim informada na cadusu.
    """
    from pending_confsib import sql_exclude_pending

    excl = sql_exclude_pending("inativo_cadusu_ativo_confsib")
    return f"""
                SELECT c.id
                FROM cadusu c
                INNER JOIN (
                    {CONFSIB_LATEST_BY_CCO}
                ) s ON s.codcco = c.codcco
                WHERE c.situusu = 'INATIVO'
                  AND TRIM(s.status) = 'A'
                  AND {COMPAT_CHAVES_CONFSIB}
                  {EXTRA_FIX_EXCLUSAO}
                  {excl}
    """


ANS_FLEX_FLAGS = (
    "ansrg",
    "anscpf",
    "ansmae",
    "anscns",
    "ansnasc",
    "ansparentesco",
    "anstitular",
    "ansnome",
    "ansplano",
    "ansdataini",
    "ansdatafim",
    "anscnpjcei",
)
ANS_FLEX_ALGUM_MARCADO = " OR ".join(
    f"COALESCE(TRIM({c}), '') = '1'" for c in ANS_FLEX_FLAGS
)
ANS_FLEX_ALGUM_MARCADO_C = " OR ".join(
    f"COALESCE(TRIM(c.{col}), '') = '1'" for col in ANS_FLEX_FLAGS
)
ANS_FLEX_OUTRO_QUE_NOME_C = " OR ".join(
    f"COALESCE(TRIM(c.{col}), '') = '1'"
    for col in ANS_FLEX_FLAGS
    if col != "ansnome"
)
ANS_FLEX_COLS = ", ".join(ANS_FLEX_FLAGS)

def _filtro_divergencia_nome_cadusu(alias: str = "c", cont: str = "ct") -> str:
    """Listar até preparar SIB-FLEX (ansnome=1 + 10-SIB-FLEX)."""
    a, t = alias, cont
    return f"""
COALESCE(TRIM({a}.codcco), '') <> ''
AND {a}.situusu <> 'INATIVO'
AND COALESCE(TRIM(s.nomeusu), '') <> ''
AND (
      UPPER(TRIM(COALESCE({a}.nomeusu, '')))
          <> UPPER(TRIM(COALESCE(s.nomeusu, '')))
   OR (
        TRIM({a}.codusu) = '00'
        AND {t}.codtit IS NOT NULL
        AND UPPER(TRIM(COALESCE({t}.nometit, '')))
            <> UPPER(TRIM(COALESCE({a}.nomeusu, '')))
   )
)
AND NOT (
      COALESCE(TRIM({a}.ansnome), '') = '1'
  AND {a}.posans = '10-SIB-FLEX'
  AND (
        TRIM({a}.codusu) <> '00'
     OR {t}.codtit IS NULL
     OR UPPER(TRIM(COALESCE({t}.nometit, '')))
        = UPPER(TRIM(COALESCE({a}.nomeusu, '')))
  )
)
"""


DIVERGENCIA_NOME_CADUSU_FILTRO = _filtro_divergencia_nome_cadusu("c", "ct")
DIVERGENCIA_NOME_CADUSU_FILTRO_C2 = _filtro_divergencia_nome_cadusu("c2", "ct")


@dataclass(frozen=True)
class SibRule:
    id: str
    category: str
    title: str
    severity: str
    description: str
    expected_zero: bool
    count_sql: str | Callable[[], str]
    detail_sql: str | Callable[[], str]


def _limit_clause() -> str:
    return f" LIMIT {Config.MAX_ROWS}"


def _resolve_sql(value: str | Callable[[], str]) -> str:
    return value() if callable(value) else value


# confsib sem vínculo em cadusu (mesmas chaves de conferência).
_CONFSIB_SEM_CADUSU_WHERE = f"""
            NOT EXISTS (
                SELECT 1 FROM cadusu c
                WHERE COALESCE(s.codcco, '') <> ''
                  AND c.codcco = s.codcco
            )
            AND NOT EXISTS (
                SELECT 1 FROM cadusu c
                WHERE COALESCE(s.codcco, '') = ''
                  AND COALESCE(s.codusu, '') <> ''
                  AND c.codans = s.codusu
                  AND {NASC_IGUAL}
            )
            AND NOT EXISTS (
                SELECT 1 FROM cadusu c
                WHERE COALESCE(s.codcco, '') = ''
                  AND COALESCE(s.cpfusu, '') <> ''
                  AND c.cpfusu = s.cpfusu
                  AND {NASC_IGUAL}
            )
"""


def _sql_confsib_sem_cadusu(status: str) -> tuple[str, str]:
    """Registros na confsib sem correspondente em cadusu, filtrados por status A/I."""
    count_sql = f"""
            SELECT COUNT(*) AS total
            FROM confsib s
            WHERE TRIM(s.status) = '{status}'
              AND {_CONFSIB_SEM_CADUSU_WHERE}
        """
    detail_sql = f"""
            SELECT s.numseq, s.status, s.codcco, s.codusu, s.nomeusu, s.cpfusu,
                   s.nascusu, s.sexousu, s.dataini, s.datafim, s.flag, s.registro
            FROM confsib s
            WHERE TRIM(s.status) = '{status}'
              AND {_CONFSIB_SEM_CADUSU_WHERE}
            ORDER BY s.nomeusu NULLS LAST, s.numseq
            {_limit_clause()}
        """
    return count_sql, detail_sql


RULES: list[SibRule] = [


    SibRule(
        id="inativo_sem_cco_nao_atualizado",
        category="POSANS / Situação",
        title="Inativo sem CCO e POSANS ≠ 4-ATUALIZADO",
        severity="critica",
        description=(
            "Beneficiário INATIVO sem CODCCO deve permanecer como 4-ATUALIZADO "
            "(nunca esteve na ANS ou já foi regularizado). Outro POSANS indica "
            "movimento SIB indevido."
        ),
        expected_zero=True,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE situusu = 'INATIVO'
              AND COALESCE(TRIM(codcco), '') = ''
              AND posans <> '4-ATUALIZADO'
        """,
        detail_sql=f"""
            SELECT {CADUSU_COLS} FROM cadusu
            WHERE situusu = 'INATIVO'
              AND COALESCE(TRIM(codcco), '') = ''
              AND posans <> '4-ATUALIZADO'
            ORDER BY dataini NULLS LAST, codtit, codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="ativo_com_cco_inclusao",
        category="POSANS / Situação",
        title="Ativo com CCO e POSANS = 1-INCLUSAO",
        severity="critica",
        description=(
            "Se situusu = ATIVO e possui CODCCO, o POSANS não pode ser 1-INCLUSAO. "
            "Quem já tem vínculo na ANS deve estar 4-ATUALIZADO "
            "(ou 2-ALTERACAO / 10-SIB-FLEX se houver sincronização)."
        ),
        expected_zero=True,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE situusu = 'ATIVO'
              AND COALESCE(TRIM(codcco), '') <> ''
              AND posans = '1-INCLUSAO'
        """,
        detail_sql=f"""
            SELECT {CADUSU_COLS} FROM cadusu
            WHERE situusu = 'ATIVO'
              AND COALESCE(TRIM(codcco), '') <> ''
              AND posans = '1-INCLUSAO'
            ORDER BY dataini NULLS LAST, codtit, codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="inativo_cco_null_exclusao",
        category="POSANS / Situação",
        title="Inativo com CCO nulo e POSANS = 3-EXCLUSAO",
        severity="critica",
        description=(
            "Não é possível excluir no SIB um beneficiário sem CODCCO. "
            "Exclusão exige vínculo prévio com a ANS."
        ),
        expected_zero=True,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE situusu = 'INATIVO'
              AND codcco IS NULL
              AND posans = '3-EXCLUSAO'
        """,
        detail_sql=f"""
            SELECT {CADUSU_COLS} FROM cadusu
            WHERE situusu = 'INATIVO'
              AND codcco IS NULL
              AND posans = '3-EXCLUSAO'
            ORDER BY datafim NULLS LAST, codtit, codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="inativo_cco_null_inclusao",
        category="POSANS / Situação",
        title="Inativo com CCO nulo e POSANS = 1-INCLUSAO",
        severity="critica",
        description=(
            "Inclusão SIB não se aplica a beneficiário INATIVO. "
            "Ajuste situação ou POSANS conforme o ciclo de vida."
        ),
        expected_zero=True,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE situusu = 'INATIVO'
              AND codcco IS NULL
              AND posans = '1-INCLUSAO'
        """,
        detail_sql=f"""
            SELECT {CADUSU_COLS} FROM cadusu
            WHERE situusu = 'INATIVO'
              AND codcco IS NULL
              AND posans = '1-INCLUSAO'
            ORDER BY dataini NULLS LAST, codtit, codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="alteracao_com_cco",
        category="POSANS / Situação",
        title="POSANS = 2-ALTERACAO com CODCCO preenchido",
        severity="alta",
        description=(
            "Registros em 2-ALTERACAO com CODCCO preenchido indicam movimento "
            "não conciliado após envio/retorno ANS - devem ser zerados após acerto."
        ),
        expected_zero=True,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE posans = '2-ALTERACAO'
              AND COALESCE(TRIM(codcco), '') <> ''
        """,
        detail_sql=f"""
            SELECT {CADUSU_COLS} FROM cadusu
            WHERE posans = '2-ALTERACAO'
              AND COALESCE(TRIM(codcco), '') <> ''
            ORDER BY dataalt NULLS LAST, dataini NULLS LAST, codtit, codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="reinclusao_antiga_com_cco",
        category="Prazos SIB",
        title="Reinclusão (>90 dias) com CODCCO preenchido",
        severity="alta",
        description=(
            "POSANS 8-REINCLUSAO com DATAINI há mais de 90 dias e CODCCO preenchido "
            "indica reinclusão travada - prazo operacional extrapolado. "
            "Correção: posans = 4-ATUALIZADO; se houver match exato com confsib "
            "(CCO+nome+CPF+nasc+dataini) e datafim na cadusu, limpa datafim. "
            "Não inclui quem está na regra "
            "'Ativo/inativo - mesmo registro (reinclusão)': nesses casos o 8-REINCLUSAO "
            "é intencional (aguardando ANS atualizar a confsib, 30+ dias) e prevalece."
        ),
        expected_zero=True,
        count_sql=f"""
            SELECT COUNT(*) AS total
            FROM cadusu c
            WHERE c.dataini < CURRENT_DATE - INTERVAL '90 days'
              AND c.posans = '8-REINCLUSAO'
              AND COALESCE(TRIM(c.codcco), '') <> ''
              {EXTRA_SEM_MESMO_REGISTRO_REINCLUSAO}
        """,
        detail_sql=f"""
            SELECT c.id, c.codtit, c.codusu, c.nomeusu, c.situusu, c.posans, c.codcco, c.codans,
                   c.cpfusu, c.nascusu, c.sexousu, c.dataini, c.datafim, c.dataexc, c.datareinc,
                   c.dataalt, c.mae, c.cns, c.codplano, c.codplaport, c.parentesco, c.datacad,
                   s.status AS status_ans, s.codcco AS cco_ans, s.codusu AS codusu_ans,
                   s.nomeusu AS nome_ans, s.cpfusu AS cpf_ans, s.nascusu AS nasc_ans,
                   s.dataini AS dataini_ans, s.datafim AS datafim_ans
            FROM cadusu c
            LEFT JOIN (
                {CONFSIB_LATEST_BY_CCO}
            ) s ON s.codcco = c.codcco
            WHERE c.dataini < CURRENT_DATE - INTERVAL '90 days'
              AND c.posans = '8-REINCLUSAO'
              AND COALESCE(TRIM(c.codcco), '') <> ''
              {EXTRA_SEM_MESMO_REGISTRO_REINCLUSAO}
            ORDER BY c.dataini, c.codtit, c.codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="inclusao_antiga_com_cco",
        category="Prazos SIB",
        title="Inclusão (>90 dias) com CODCCO preenchido",
        severity="alta",
        description=(
            "POSANS 1-INCLUSAO com DATAINI há mais de 90 dias e CODCCO preenchido "
            "não deveria persistir - a inclusão já deveria ter virado 4-ATUALIZADO."
        ),
        expected_zero=True,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE dataini < CURRENT_DATE - INTERVAL '90 days'
              AND posans = '1-INCLUSAO'
              AND COALESCE(TRIM(codcco), '') <> ''
        """,
        detail_sql=f"""
            SELECT {CADUSU_COLS} FROM cadusu
            WHERE dataini < CURRENT_DATE - INTERVAL '90 days'
              AND posans = '1-INCLUSAO'
              AND COALESCE(TRIM(codcco), '') <> ''
            ORDER BY dataini, codtit, codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="reinclusao_recente_com_cco",
        category="Prazos SIB",
        title="Reinclusão (≤90 dias) com CODCCO preenchido",
        severity="alta",
        description=(
            "Em 8-REINCLUSAO recente com CODCCO já preenchido, o status POSANS "
            "está inconsistente com o vínculo ANS existente."
        ),
        expected_zero=True,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE dataini >= CURRENT_DATE - INTERVAL '90 days'
              AND posans = '8-REINCLUSAO'
              AND COALESCE(TRIM(codcco), '') <> ''
        """,
        detail_sql=f"""
            SELECT {CADUSU_COLS} FROM cadusu
            WHERE dataini >= CURRENT_DATE - INTERVAL '90 days'
              AND posans = '8-REINCLUSAO'
              AND COALESCE(TRIM(codcco), '') <> ''
            ORDER BY dataini DESC, codtit, codusu
            {_limit_clause()}
        """,
    ),


    SibRule(
        id="cadusu_ausente_confsib",
        category="Conferência ANS (confsib)",
        title="Beneficiário em cadusu ausente na confsib",
        severity="critica",
        description=(
            "Beneficiário da cadusu (exceto INATIVO) deve constar na confsib "
            "(arquivo de conferência ANS), salvo ATIVO com CODCCO preenchido e "
            "POSANS = 1-INCLUSAO. "
            "Chaves: 1) CODCCO; 2) CODANS=CODUSU + nascimento; 3) CPF + nascimento."
        ),
        expected_zero=True,
        count_sql=f"""
            SELECT COUNT(*) AS total
            FROM cadusu c
            WHERE c.situusu <> 'INATIVO'
            AND NOT (
                c.situusu = 'ATIVO'
                AND COALESCE(c.codcco, '') <> ''
                AND c.posans = '1-INCLUSAO'
            )
            AND NOT EXISTS (
                SELECT 1 FROM confsib s
                WHERE COALESCE(c.codcco, '') <> ''
                  AND s.codcco = c.codcco
            )
            AND NOT EXISTS (
                SELECT 1 FROM confsib s
                WHERE COALESCE(c.codcco, '') = ''
                  AND COALESCE(c.codans, '') <> ''
                  AND s.codusu = c.codans
                  AND {NASC_IGUAL}
            )
            AND NOT EXISTS (
                SELECT 1 FROM confsib s
                WHERE COALESCE(c.codcco, '') = ''
                  AND COALESCE(c.cpfusu, '') <> ''
                  AND s.cpfusu = c.cpfusu
                  AND {NASC_IGUAL}
            )
        """,
        detail_sql=f"""
            SELECT c.id, c.codtit, c.codusu, c.nomeusu, c.situusu, c.posans, c.codcco, c.codans,
                   c.cpfusu, c.nascusu, c.sexousu, c.dataini, c.datafim, c.dataexc, c.datareinc,
                   c.dataalt, c.mae, c.cns, c.codplano, c.codplaport, c.parentesco, c.datacad
            FROM cadusu c
            WHERE c.situusu <> 'INATIVO'
            AND NOT (
                c.situusu = 'ATIVO'
                AND COALESCE(c.codcco, '') <> ''
                AND c.posans = '1-INCLUSAO'
            )
            AND NOT EXISTS (
                SELECT 1 FROM confsib s
                WHERE COALESCE(c.codcco, '') <> ''
                  AND s.codcco = c.codcco
            )
            AND NOT EXISTS (
                SELECT 1 FROM confsib s
                WHERE COALESCE(c.codcco, '') = ''
                  AND COALESCE(c.codans, '') <> ''
                  AND s.codusu = c.codans
                  AND {NASC_IGUAL}
            )
            AND NOT EXISTS (
                SELECT 1 FROM confsib s
                WHERE COALESCE(c.codcco, '') = ''
                  AND COALESCE(c.cpfusu, '') <> ''
                  AND s.cpfusu = c.cpfusu
                  AND {NASC_IGUAL}
            )
            ORDER BY c.situusu, c.posans, c.codtit, c.codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="confsib_sem_cadusu",
        category="Conferência ANS (confsib)",
        title="Registro ativo na confsib sem correspondente em cadusu",
        severity="alta",
        description=(
            "Beneficiário ATIVO no retorno ANS (confsib.status = A) sem vínculo local "
            "em cadusu. "
            "Chaves: 1) CODCCO; 2) CODUSU=CODANS + nascimento; 3) CPF + nascimento. "
            "Inativos sem cadusu estão na regra separada "
            "'Registro inativo na confsib sem correspondente em cadusu'."
        ),
        expected_zero=True,
        count_sql=_sql_confsib_sem_cadusu("A")[0],
        detail_sql=_sql_confsib_sem_cadusu("A")[1],
    ),
    SibRule(
        id="confsib_sem_cadusu_inativo",
        category="Conferência ANS (confsib)",
        title="Registro inativo na confsib sem correspondente em cadusu",
        severity="media",
        description=(
            "Beneficiário INATIVO no retorno ANS (confsib.status = I) sem vínculo local "
            "em cadusu. "
            "Chaves: 1) CODCCO; 2) CODUSU=CODANS + nascimento; 3) CPF + nascimento. "
            "Em geral é legado/baixa já processada na ANS sem espelho local; "
            "avaliar se precisa cadastro histórico ou pode ser ignorado."
        ),
        expected_zero=True,
        count_sql=_sql_confsib_sem_cadusu("I")[0],
        detail_sql=_sql_confsib_sem_cadusu("I")[1],
    ),
    SibRule(
        id="inativo_cadusu_ativo_confsib",
        category="Conferência ANS (confsib)",
        title="Inativo na cadusu e ativo na confsib",
        severity="critica",
        description=(
            "Beneficiário INATIVO na base local (cadusu) mas ATIVO no retorno ANS "
            "(confsib.status = A). "
            "Lista somente quando o mesmo registro é certificado pela chave CCO "
            "(com compatibilidade de CPF/nome/nascimento quando preenchidos). "
            "Correção automática (somente com datafim na cadusu): posans = 3-EXCLUSAO "
            "para envio da exclusão no próximo SIB. Sem datafim não há UPDATE. "
            "Apos aplicar, o id entra no controle local "
            "'aguardando retorno confsib' (SQLite, ~45 dias) e deixa de ser listado "
            "para evitar reaplicacao; a confsib so reflete INATIVO apos o processamento ANS. "
            "Quem ja esta em 3-EXCLUSAO nao entra nesta regra."
        ),
        expected_zero=True,
        count_sql=lambda: _sql_inativo_ativo_por_cco(_EXTRA_SEM_EXCLUSAO_PENDENTE)[0],
        detail_sql=lambda: _sql_inativo_ativo_por_cco(_EXTRA_SEM_EXCLUSAO_PENDENTE)[1],
    ),
    SibRule(
        id="ativo_cadusu_inativo_confsib",
        category="Conferência ANS (confsib)",
        title="Ativo na cadusu e inativo na confsib",
        severity="critica",
        description=(
            "Beneficiário ATIVO na cadusu e INATIVO na confsib somente quando "
            "é a mesma pessoa: nome, CPF, nascimento, dataini e codusu/codans "
            "iguais aos da confsib. "
            "Inclusão nova (ex.: 1-INCLUSAO com dataini diferente) não entra nesta "
            "crítica - o registro local está correto. "
            "Correção: posans = 4-ATUALIZADO; se ainda sem CCO, copia o CODCCO da confsib."
        ),
        expected_zero=True,
        count_sql=_sql_ativo_cadusu_inativo_validacao_completa()[0],
        detail_sql=_sql_ativo_cadusu_inativo_validacao_completa()[1],
    ),
    SibRule(
        id="ativo_inativo_confsib_reinclusao",
        category="Conferência ANS (confsib)",
        title="Ativo/inativo - mesmo registro (reinclusão)",
        severity="critica",
        description=(
            "ATIVO na cadusu e INATIVO na confsib com o mesmo beneficiario "
            "(CCO + nome + CPF + nascimento + dataini iguais) e campos obrigatorios ANS "
            "preenchidos. "
            "Correcao: posans = 8-REINCLUSAO somente se a cadusu tiver CODCCO "
            "preenchido; sem CCO nao ha UPDATE. "
            "Apos aplicar, o id entra no controle local "
            "'aguardando retorno confsib' (SQLite, ~45 dias) e nao e listado de novo, "
            "evitando reaplicacao enquanto a ANS nao atualiza a confsib (30+ dias)."
        ),
        expected_zero=True,
        count_sql=lambda: _sql_ativo_inativo_mesmo_registro()[0],
        detail_sql=lambda: _sql_ativo_inativo_mesmo_registro()[1],
    ),


    SibRule(
        id="ativo_sem_cco_fora_inclusao",
        category="POSANS / Situação",
        title="Ativo sem CCO fora de inclusão",
        severity="critica",
        description=(
            "Beneficiário ATIVO sem CODCCO e com CPF deve estar em 1-INCLUSAO. "
            "Sem CCO não há reinclusão na ANS (8-REINCLUSAO exige vínculo prévio/CCO); "
            "esses casos devem ser enviados como inclusão. "
            "Lista somente quando o prazo ANS da dataini já venceu "
            "(envio até o dia 5 do mês seguinte à competência da dataini). "
            "Ex.: dataini 01/10/2026 — prazo até 05/11/2026; não lista antes disso. "
            "Sem CPF não se envia inclusão à ANS (não atribui CCO); esses casos são tratados "
            "na regra 'Ativo sem CPF' (posans = 4-ATUALIZADO)."
        ),
        expected_zero=True,
        count_sql=f"""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE situusu = 'ATIVO'
              AND COALESCE(TRIM(codcco), '') = ''
              AND COALESCE(TRIM(cpfusu), '') <> ''
              AND posans <> '1-INCLUSAO'
              AND {PRAZO_ENVIO_DATAINI_VENCIDO}
        """,
        detail_sql=f"""
            SELECT {CADUSU_COLS} FROM cadusu
            WHERE situusu = 'ATIVO'
              AND COALESCE(TRIM(codcco), '') = ''
              AND COALESCE(TRIM(cpfusu), '') <> ''
              AND posans <> '1-INCLUSAO'
              AND {PRAZO_ENVIO_DATAINI_VENCIDO}
            ORDER BY posans, dataini NULLS LAST, codtit, codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="ativo_com_cco_exclusao",
        category="POSANS / Situação",
        title="Ativo com POSANS = 3-EXCLUSAO",
        severity="critica",
        description=(
            "Se situusu = ATIVO, o POSANS não pode ser 3-EXCLUSAO. "
            "Exclusão SIB exige beneficiário INATIVO (ou ajuste do POSANS)."
        ),
        expected_zero=True,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE situusu = 'ATIVO'
              AND posans = '3-EXCLUSAO'
        """,
        detail_sql=f"""
            SELECT {CADUSU_COLS} FROM cadusu
            WHERE situusu = 'ATIVO'
              AND posans = '3-EXCLUSAO'
            ORDER BY datafim NULLS LAST, codtit, codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="cadusu_sem_codans",
        category="Integridade",
        title="Beneficiário sem CODANS",
        severity="critica",
        description=(
            "Todo registro em cadusu deve possuir CODANS preenchido "
            "(código do beneficiário na operadora/ANS). Ausência impede "
            "cruzamento com confsib e envios SIB. "
            "Correção: (1) INATIVO com mesmo CODCCO+CPF+DATAINI na confsib → "
            "copiar confsib.codusu; (2) sem match → montar codtit || '-' || codusu "
            "(ex.: 2741-0001 + 01 → 2741-0001-01)."
        ),
        expected_zero=True,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE COALESCE(TRIM(codans), '') = ''
        """,
        detail_sql=f"""
            SELECT {CADUSU_COLS} FROM cadusu
            WHERE COALESCE(TRIM(codans), '') = ''
            ORDER BY situusu, posans, codtit, codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="inativo_com_cco_nao_excluido",
        category="POSANS / Situação",
        title="Inativo com CCO sem exclusão/atualização",
        severity="alta",
        description=(
            "INATIVO com CODCCO deve estar em 3-EXCLUSAO (pendente) ou 4-ATUALIZADO "
            "(já excluído/conciliado na ANS). Outros POSANS geram divergência no SIB. "
            "Pré-checagem confsib: se o CCO já está INATIVO na ANS (status=I), "
            "a correção é 4-ATUALIZADO (não gerar 3-EXCLUSAO). "
            "Só sugere 3-EXCLUSAO quando a confsib ainda está ATIVA (status=A) "
            "ou quando não há retorno confsib para o CCO."
        ),
        expected_zero=True,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE situusu = 'INATIVO'
              AND COALESCE(TRIM(codcco), '') <> ''
              AND posans NOT IN ('3-EXCLUSAO', '4-ATUALIZADO')
        """,
        detail_sql=f"""
            SELECT c.id, c.codtit, c.codusu, c.nomeusu, c.situusu, c.posans,
                   c.codcco, c.codans, c.cpfusu, c.nascusu, c.sexousu,
                   c.dataini, c.datafim, c.dataexc, c.datareinc, c.dataalt,
                   c.mae, c.cns, c.codplano, c.codplaport, c.parentesco, c.datacad,
                   s.status AS status_ans,
                   CASE
                     WHEN s.codcco IS NOT NULL AND TRIM(s.status) = 'I'
                       THEN 'confsib ja inativa -> 4-ATUALIZADO'
                     WHEN s.codcco IS NOT NULL AND TRIM(s.status) = 'A'
                       THEN 'confsib ativa -> 3-EXCLUSAO'
                     ELSE 'sem confsib -> 3-EXCLUSAO'
                   END AS sugestao_posans
            FROM cadusu c
            LEFT JOIN (
                {CONFSIB_LATEST_BY_CCO}
            ) s ON s.codcco = c.codcco
            WHERE c.situusu = 'INATIVO'
              AND COALESCE(TRIM(c.codcco), '') <> ''
              AND c.posans NOT IN ('3-EXCLUSAO', '4-ATUALIZADO')
            ORDER BY c.posans, c.datafim NULLS LAST, c.codtit, c.codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="exclusao_cco_ja_inativo_confsib",
        category="Conferência ANS (confsib)",
        title="Exclusão com CCO já inativo na confsib",
        severity="alta",
        description=(
            "POSANS = 3-EXCLUSAO com o mesmo CCO já INATIVO na confsib (status=I). "
            "A ANS rejeita exclusão de quem já está inativo ('CCO já inativo'). "
            "Correção: posans = 4-ATUALIZADO (sem reenviar 3-EXCLUSAO). "
            "Espelha a conciliação local após baixa confirmada na ANS."
        ),
        expected_zero=True,
        count_sql=f"""
            SELECT COUNT(*) AS total
            FROM cadusu c
            INNER JOIN (
                {CONFSIB_LATEST_BY_CCO}
            ) s ON s.codcco = c.codcco
            WHERE c.posans = '3-EXCLUSAO'
              AND COALESCE(TRIM(c.codcco), '') <> ''
              AND TRIM(s.status) = 'I'
        """,
        detail_sql=f"""
            SELECT c.id, c.codtit, c.codusu, c.nomeusu, c.situusu, c.posans,
                   c.codcco, c.codans, c.cpfusu, c.nascusu, c.dataini, c.datafim,
                   s.status AS status_ans, s.nomeusu AS nome_ans,
                   s.datafim AS datafim_ans,
                   'CCO ja inativo na ANS - nao reenviar 3-EXCLUSAO'::text
                     AS situacao_exclusao
            FROM cadusu c
            INNER JOIN (
                {CONFSIB_LATEST_BY_CCO}
            ) s ON s.codcco = c.codcco
            WHERE c.posans = '3-EXCLUSAO'
              AND COALESCE(TRIM(c.codcco), '') <> ''
              AND TRIM(s.status) = 'I'
            ORDER BY c.situusu, c.datafim NULLS LAST, c.codtit, c.codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="exclusao_sem_datafim",
        category="Datas obrigatórias",
        title="Exclusão sem data de fim (DATAFIM) - INATIVO",
        severity="alta",
        description=(
            "INATIVO com POSANS 3-EXCLUSAO exige DATAFIM preenchida "
            "(data de cancelamento do vínculo no SIB). "
            "Correção manual: preencher datafim (não há UPDATE automático)."
        ),
        expected_zero=True,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE situusu = 'INATIVO'
              AND posans = '3-EXCLUSAO'
              AND datafim IS NULL
        """,
        detail_sql=f"""
            SELECT {CADUSU_COLS} FROM cadusu
            WHERE situusu = 'INATIVO'
              AND posans = '3-EXCLUSAO'
              AND datafim IS NULL
            ORDER BY codtit, codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="exclusao_sem_datafim_nao_inativo",
        category="POSANS / Situação",
        title="3-EXCLUSAO com situusu ≠ INATIVO - ajustar POSANS",
        severity="alta",
        description=(
            "POSANS 3-EXCLUSAO com situusu ≠ INATIVO (ex.: BLOQUEADO) e CODCCO válido: "
            "erro de cadastro - usuário bloqueou o beneficiário e setou 3-EXCLUSAO "
            "indevidamente. Correção: posans = 4-ATUALIZADO."
        ),
        expected_zero=True,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE situusu <> 'INATIVO'
              AND posans = '3-EXCLUSAO'
              AND datafim IS NULL
              AND COALESCE(TRIM(codcco), '') <> ''
        """,
        detail_sql=f"""
            SELECT {CADUSU_COLS} FROM cadusu
            WHERE situusu <> 'INATIVO'
              AND posans = '3-EXCLUSAO'
              AND datafim IS NULL
              AND COALESCE(TRIM(codcco), '') <> ''
            ORDER BY situusu, codtit, codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="inclusao_sem_dataini",
        category="Datas obrigatórias",
        title="Inclusão/reinclusão sem DATAINI",
        severity="alta",
        description="Inclusão e reinclusão no SIB exigem data de início de vigência (DATAINI).",
        expected_zero=True,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE posans IN ('1-INCLUSAO', '8-REINCLUSAO')
              AND dataini IS NULL
        """,
        detail_sql=f"""
            SELECT {CADUSU_COLS} FROM cadusu
            WHERE posans IN ('1-INCLUSAO', '8-REINCLUSAO')
              AND dataini IS NULL
            ORDER BY situusu, codtit, codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="ativo_campos_sib_obrigatorios",
        category="Dados cadastrais SIB",
        title="Ativo com campos SIB obrigatórios ausentes",
        severity="alta",
        description=(
            "ATIVO sem nome, nascimento, sexo ou CPF/CNS. "
            "Correção: se confsib tiver o mesmo cpfusu + dataini + nomeusu + nascusu, "
            "copiar os campos faltantes; com tudo preenchido e CODCCO → posans = 4-ATUALIZADO; "
            "com tudo preenchido sem CODCCO → posans = 1-INCLUSAO."
        ),
        expected_zero=True,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE situusu = 'ATIVO'
              AND (
                   COALESCE(TRIM(nomeusu), '') = ''
                OR nascusu IS NULL
                OR COALESCE(TRIM(sexousu), '') = ''
                OR (
                    COALESCE(TRIM(cpfusu), '') = ''
                    AND COALESCE(TRIM(cns), '') = ''
                )
              )
        """,
        detail_sql=f"""
            SELECT {CADUSU_COLS} FROM cadusu
            WHERE situusu = 'ATIVO'
              AND (
                   COALESCE(TRIM(nomeusu), '') = ''
                OR nascusu IS NULL
                OR COALESCE(TRIM(sexousu), '') = ''
                OR (
                    COALESCE(TRIM(cpfusu), '') = ''
                    AND COALESCE(TRIM(cns), '') = ''
                )
              )
            ORDER BY codtit, codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="ativo_sem_cpf_posans",
        category="POSANS / Situação",
        title="Ativo sem CPF",
        severity="alta",
        description=(
            "Beneficiário ATIVO sem CPF (cpfusu vazio). "
            "Correção operacional: posans = 4-ATUALIZADO. "
            "Não usar 1-INCLUSAO sem CPF - a ANS não acata o cadastro para atribuir CCO."
        ),
        expected_zero=True,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE situusu = 'ATIVO'
              AND COALESCE(TRIM(cpfusu), '') = ''
        """,
        detail_sql=f"""
            SELECT {CADUSU_COLS} FROM cadusu
            WHERE situusu = 'ATIVO'
              AND COALESCE(TRIM(cpfusu), '') = ''
            ORDER BY posans, codtit, codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="cpf_invalido_ativo",
        category="Dados cadastrais SIB",
        title="Ativo com CPF em formato inválido",
        severity="media",
        description=(
            "CPF informado deve conter exatamente 11 dígitos numéricos "
            "(sem máscara). Formatos inválidos são rejeitados pela ANS."
        ),
        expected_zero=True,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE situusu = 'ATIVO'
              AND COALESCE(TRIM(cpfusu), '') <> ''
              AND (
                    LENGTH(REGEXP_REPLACE(cpfusu, '[^0-9]', '', 'g')) <> 11
                 OR cpfusu !~ '^[0-9]{11}$'
              )
        """,
        detail_sql=f"""
            SELECT {CADUSU_COLS} FROM cadusu
            WHERE situusu = 'ATIVO'
              AND COALESCE(TRIM(cpfusu), '') <> ''
              AND (
                    LENGTH(REGEXP_REPLACE(cpfusu, '[^0-9]', '', 'g')) <> 11
                 OR cpfusu !~ '^[0-9]{{11}}$'
              )
            ORDER BY codtit, codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="nome_mae_invalido",
        category="Integridade",
        title="Nome ou mãe inválidos (dígitos / mãe sem sobrenome)",
        severity="critica",
        description=(
            "Somente beneficiários ATIVOS na cadusu. "
            "nomeusu e mae devem conter somente letras "
            "(espaços, hífen e apóstrofo permitidos) - números e outros "
            "caracteres são inválidos. "
            "mae, quando preenchida, exige no mínimo nome e sobrenome "
            "(não aceita valor de uma só palavra, ex.: MARIA)."
        ),
        expected_zero=True,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE situusu = 'ATIVO'
              AND (
                    (
                        COALESCE(TRIM(nomeusu), '') <> ''
                    AND nomeusu ~ '[^[:alpha:][:space:]''\\-]'
                    )
                OR (
                        COALESCE(TRIM(mae), '') <> ''
                    AND mae ~ '[^[:alpha:][:space:]''\\-]'
                    )
                OR (
                        COALESCE(TRIM(mae), '') <> ''
                    AND array_length(
                            regexp_split_to_array(btrim(mae), '[[:space:]]+'),
                            1
                        ) < 2
                    )
              )
        """,
        detail_sql=f"""
            SELECT id, codtit, codusu, nomeusu, mae, situusu, posans,
                   codcco, codans, cpfusu, nascusu, dataini,
                   CASE
                     WHEN COALESCE(TRIM(nomeusu), '') <> ''
                          AND nomeusu ~ '[0-9]'
                       THEN 'nomeusu com digito'
                     WHEN COALESCE(TRIM(nomeusu), '') <> ''
                          AND nomeusu ~ '[^[:alpha:][:space:]''\\-]'
                       THEN 'nomeusu com caractere invalido'
                     ELSE NULL
                   END AS problema_nomeusu,
                   CASE
                     WHEN COALESCE(TRIM(mae), '') <> ''
                          AND mae ~ '[0-9]'
                       THEN 'mae com digito'
                     WHEN COALESCE(TRIM(mae), '') <> ''
                          AND mae ~ '[^[:alpha:][:space:]''\\-]'
                       THEN 'mae com caractere invalido'
                     WHEN COALESCE(TRIM(mae), '') <> ''
                          AND array_length(
                                regexp_split_to_array(btrim(mae), '[[:space:]]+'),
                                1
                              ) < 2
                       THEN 'mae sem sobrenome'
                     ELSE NULL
                   END AS problema_mae
            FROM cadusu
            WHERE situusu = 'ATIVO'
              AND (
                    (
                        COALESCE(TRIM(nomeusu), '') <> ''
                    AND nomeusu ~ '[^[:alpha:][:space:]''\\-]'
                    )
                OR (
                        COALESCE(TRIM(mae), '') <> ''
                    AND mae ~ '[^[:alpha:][:space:]''\\-]'
                    )
                OR (
                        COALESCE(TRIM(mae), '') <> ''
                    AND array_length(
                            regexp_split_to_array(btrim(mae), '[[:space:]]+'),
                            1
                        ) < 2
                    )
              )
            ORDER BY codtit, codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="cco_duplicado",
        category="Integridade",
        title="CODCCO duplicado em cadusu",
        severity="critica",
        description=(
            "O CCO é identificador único do beneficiário na ANS. "
            "Duplicidade local gera rejeição e inconsistência na conferência. "
            "Ignora INATIVO e registros sem CODCCO."
        ),
        expected_zero=True,
        count_sql="""
            SELECT COUNT(*) AS total FROM (
                SELECT TRIM(codcco) AS cco
                FROM cadusu
                WHERE situusu <> 'INATIVO'
                  AND COALESCE(TRIM(codcco), '') <> ''
                GROUP BY TRIM(codcco)
                HAVING COUNT(*) > 1
            ) d
        """,
        detail_sql=f"""
            SELECT {CADUSU_COLS}
            FROM cadusu
            WHERE situusu <> 'INATIVO'
              AND COALESCE(TRIM(codcco), '') <> ''
              AND TRIM(codcco) IN (
                SELECT TRIM(codcco)
                FROM cadusu
                WHERE situusu <> 'INATIVO'
                  AND COALESCE(TRIM(codcco), '') <> ''
                GROUP BY TRIM(codcco)
                HAVING COUNT(*) > 1
              )
            ORDER BY codcco, situusu, codtit, codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="cpf_inclusao_ja_ativo_confsib",
        category="Conferência ANS (confsib)",
        title="Inclusão com CPF já ativo na confsib",
        severity="critica",
        description=(
            "ATIVO em 1-INCLUSAO sem CCO cujo CPF já existe ativo na confsib "
            "(status=A) e é a mesma pessoa (dataini e nome iguais). "
            "Nesses casos a ANS rejeitaria a inclusão: a correção copia o "
            "CODCCO da confsib e define posans = 4-ATUALIZADO. "
            "Se dataini (ou nome) divergir, trata-se de inclusão nova válida "
            "e o registro não entra nesta crítica."
        ),
        expected_zero=True,
        count_sql=f"""
            SELECT COUNT(*) AS total FROM (
                SELECT c.id
                FROM cadusu c
                INNER JOIN LATERAL (
                    SELECT s0.*
                    FROM confsib s0
                    WHERE TRIM(COALESCE(s0.cpfusu, '')) = TRIM(COALESCE(c.cpfusu, ''))
                      AND TRIM(s0.status) = 'A'
                      AND COALESCE(TRIM(s0.codcco), '') <> ''
                    ORDER BY s0.numseq DESC
                    LIMIT 1
                ) s ON TRUE
                WHERE c.situusu = 'ATIVO'
                  AND c.posans = '1-INCLUSAO'
                  AND COALESCE(TRIM(c.codcco), '') = ''
                  AND LENGTH(
                        REGEXP_REPLACE(COALESCE(c.cpfusu, ''), '[^0-9]', '', 'g')
                      ) = 11
                  AND {DATAINI_IGUAL_CONFSIB}
                  AND COALESCE(TRIM(c.nomeusu), '') <> ''
                  AND COALESCE(TRIM(s.nomeusu), '') <> ''
                  AND UPPER(TRIM(c.nomeusu)) = UPPER(TRIM(s.nomeusu))
            ) q
        """,
        detail_sql=f"""
            SELECT c.id, c.codtit, c.codusu, c.nomeusu, c.situusu, c.posans,
                   c.cpfusu, c.nascusu, c.codplano, c.codcco, c.codans, c.dataini,
                   ({DATAINI_CONFSIB}) AS dataini_ans,
                   s.codcco AS cco_conflito,
                   s.codusu AS codusu_conflito,
                   s.codtit AS codtit_conflito,
                   s.nomeusu AS nome_conflito,
                   s.codplaport AS plano_conflito,
                   s.codplaope AS plano_ope_conflito,
                   s.cnpj AS cnpj_contratante_ans,
                   s.status AS status_ans,
                   'mesma pessoa - vincular CCO + 4-ATUALIZADO'::text
                     AS situacao_inclusao
            FROM cadusu c
            INNER JOIN LATERAL (
                SELECT s0.*
                FROM confsib s0
                WHERE TRIM(COALESCE(s0.cpfusu, '')) = TRIM(COALESCE(c.cpfusu, ''))
                  AND TRIM(s0.status) = 'A'
                  AND COALESCE(TRIM(s0.codcco), '') <> ''
                ORDER BY s0.numseq DESC
                LIMIT 1
            ) s ON TRUE
            WHERE c.situusu = 'ATIVO'
              AND c.posans = '1-INCLUSAO'
              AND COALESCE(TRIM(c.codcco), '') = ''
              AND LENGTH(
                    REGEXP_REPLACE(COALESCE(c.cpfusu, ''), '[^0-9]', '', 'g')
                  ) = 11
              AND {DATAINI_IGUAL_CONFSIB}
              AND COALESCE(TRIM(c.nomeusu), '') <> ''
              AND COALESCE(TRIM(s.nomeusu), '') <> ''
              AND UPPER(TRIM(c.nomeusu)) = UPPER(TRIM(s.nomeusu))
            ORDER BY c.dataini DESC NULLS LAST, c.codtit, c.codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="cpf_duplicado_ativos",
        category="Integridade",
        title="CPF duplicado entre ATIVOS na mesma empresa",
        severity="alta",
        description=(
            "Dois ou mais ATIVOS com o mesmo CPF na mesma empresa "
            "(4 primeiros dígitos de CODTIT). CPF repetido em empresas "
            "diferentes é permitido. "
            "Para conflito com vínculo já ativo na ANS (inclusão SIB), use a regra "
            "'Inclusão com CPF já ativo na confsib'."
        ),
        expected_zero=True,
        count_sql="""
            SELECT COUNT(*) AS total
            FROM cadusu c
            WHERE c.situusu = 'ATIVO'
              AND COALESCE(TRIM(c.cpfusu), '') <> ''
              AND c.cpfusu ~ '^[0-9]{11}$'
              AND LENGTH(COALESCE(c.codtit, '')) >= 4
              AND EXISTS (
                SELECT 1 FROM cadusu c2
                WHERE c2.situusu = 'ATIVO'
                  AND COALESCE(TRIM(c2.cpfusu), '') <> ''
                  AND c2.cpfusu ~ '^[0-9]{11}$'
                  AND TRIM(c2.cpfusu) = TRIM(c.cpfusu)
                  AND LEFT(c2.codtit, 4) = LEFT(c.codtit, 4)
                  AND c2.id <> c.id
              )
        """,
        detail_sql=f"""
            SELECT c.id,
                   LEFT(c.codtit, 4) AS empresa,
                   c.codtit, c.codusu, c.nomeusu, c.situusu, c.posans,
                   c.codcco, c.codans, c.cpfusu, c.nascusu, c.sexousu,
                   c.dataini, c.datafim, c.codplano, c.parentesco
            FROM cadusu c
            WHERE c.situusu = 'ATIVO'
              AND COALESCE(TRIM(c.cpfusu), '') <> ''
              AND c.cpfusu ~ '^[0-9]{{11}}$'
              AND LENGTH(COALESCE(c.codtit, '')) >= 4
              AND EXISTS (
                SELECT 1 FROM cadusu c2
                WHERE c2.situusu = 'ATIVO'
                  AND COALESCE(TRIM(c2.cpfusu), '') <> ''
                  AND c2.cpfusu ~ '^[0-9]{{11}}$'
                  AND TRIM(c2.cpfusu) = TRIM(c.cpfusu)
                  AND LEFT(c2.codtit, 4) = LEFT(c.codtit, 4)
                  AND c2.id <> c.id
              )
            ORDER BY c.cpfusu, LEFT(c.codtit, 4), c.nascusu NULLS LAST, c.codtit, c.codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="cpf_duplicado_ativos_nasc_divergente",
        category="Integridade",
        title="CPF duplicado (mesma empresa) com nascimento divergente",
        severity="critica",
        description=(
            "Mesmo CPF entre ATIVOS na mesma empresa (LEFT(CODTIT,4)), "
            "porém com datas de nascimento diferentes. Indica CPF inválido "
            "ou cadastrado em pessoas distintas - exige correção prioritária."
        ),
        expected_zero=True,
        count_sql="""
            SELECT COUNT(*) AS total
            FROM cadusu c
            WHERE c.situusu = 'ATIVO'
              AND COALESCE(TRIM(c.cpfusu), '') <> ''
              AND c.cpfusu ~ '^[0-9]{11}$'
              AND LENGTH(COALESCE(c.codtit, '')) >= 4
              AND EXISTS (
                SELECT 1 FROM cadusu c2
                WHERE c2.situusu = 'ATIVO'
                  AND COALESCE(TRIM(c2.cpfusu), '') <> ''
                  AND c2.cpfusu ~ '^[0-9]{11}$'
                  AND TRIM(c2.cpfusu) = TRIM(c.cpfusu)
                  AND LEFT(c2.codtit, 4) = LEFT(c.codtit, 4)
                  AND c2.id <> c.id
                  AND c.nascusu IS DISTINCT FROM c2.nascusu
              )
        """,
        detail_sql=f"""
            SELECT c.id,
                   LEFT(c.codtit, 4) AS empresa,
                   c.codtit, c.codusu, c.nomeusu, c.cpfusu, c.nascusu,
                   c.situusu, c.posans, c.codcco, c.codans, c.sexousu,
                   c.dataini, c.datafim,
                   (
                     SELECT STRING_AGG(
                       DISTINCT COALESCE(TO_CHAR(c3.nascusu, 'DD/MM/YYYY'), '(sem data)'),
                       ' | '
                       ORDER BY COALESCE(TO_CHAR(c3.nascusu, 'DD/MM/YYYY'), '(sem data)')
                     )
                     FROM cadusu c3
                     WHERE c3.situusu = 'ATIVO'
                       AND TRIM(c3.cpfusu) = TRIM(c.cpfusu)
                       AND LEFT(c3.codtit, 4) = LEFT(c.codtit, 4)
                   ) AS nascimentos_do_cpf
            FROM cadusu c
            WHERE c.situusu = 'ATIVO'
              AND COALESCE(TRIM(c.cpfusu), '') <> ''
              AND c.cpfusu ~ '^[0-9]{{11}}$'
              AND LENGTH(COALESCE(c.codtit, '')) >= 4
              AND EXISTS (
                SELECT 1 FROM cadusu c2
                WHERE c2.situusu = 'ATIVO'
                  AND COALESCE(TRIM(c2.cpfusu), '') <> ''
                  AND c2.cpfusu ~ '^[0-9]{{11}}$'
                  AND TRIM(c2.cpfusu) = TRIM(c.cpfusu)
                  AND LEFT(c2.codtit, 4) = LEFT(c.codtit, 4)
                  AND c2.id <> c.id
                  AND c.nascusu IS DISTINCT FROM c2.nascusu
              )
            ORDER BY c.cpfusu, LEFT(c.codtit, 4), c.nascusu NULLS LAST, c.codtit, c.codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="cpf_invalido_cruzado_nascimento",
        category="Integridade",
        title="CPF inválido para a data de nascimento",
        severity="critica",
        description=(
            "Heurística equivalente à consulta RF (CPF + nascimento): na mesma empresa, "
            "o CPF aparece em ATIVOS com nascimentos diferentes. Mantém-se o CPF no "
            "cadastro mais antigo (desempate: titular 00); os demais são tratados como "
            "CPF inválido para aquele nascimento (ex.: dependente com CPF do titular). "
            "Correção sugerida: limpar CPF (NULL)."
        ),
        expected_zero=True,
        count_sql="""
            WITH base AS (
                SELECT id, codtit, codusu, nomeusu, cpfusu, nascusu,
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
        detail_sql=f"""
            WITH base AS (
                SELECT id, codtit, codusu, nomeusu, cpfusu, nascusu, dataini,
                       situusu, posans, codcco, codans,
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
                       b.id AS id_mantido,
                       b.empresa, b.cpf,
                       b.cpfusu AS cpf_mantido,
                       b.nascusu AS nasc_mantido,
                       b.nomeusu AS nome_mantido
                FROM base b
                INNER JOIN grupos g ON g.empresa = b.empresa AND g.cpf = b.cpf
                ORDER BY b.empresa, b.cpf,
                         b.nascusu ASC NULLS LAST,
                         CASE WHEN b.codusu = '00' THEN 0 ELSE 1 END,
                         b.id
            )
            SELECT b.id, b.empresa, b.codtit, b.codusu, b.nomeusu,
                   b.codcco, b.posans, b.dataini,
                   b.cpfusu AS cpf_atual, b.nascusu,
                   k.cpf_mantido AS cpf_do_cadastro_mantido,
                   k.nasc_mantido AS nasc_do_cadastro_mantido,
                   k.nome_mantido AS nome_do_cadastro_mantido,
                   k.id_mantido,
                   b.situusu, b.codans
            FROM base b
            INNER JOIN grupos g ON g.empresa = b.empresa AND g.cpf = b.cpf
            INNER JOIN keepers k ON k.empresa = b.empresa AND k.cpf = b.cpf
            WHERE b.id <> k.id_mantido
            ORDER BY b.cpf, b.empresa, b.nascusu NULLS LAST, b.codtit, b.codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="divergencia_nome_cadusu_confsib",
        category="Conferência ANS (confsib)",
        title="Divergência de nome (não INATIVO) - manter cadusu (RF humano)",
        severity="alta",
        description=(
            "Mesmo CODCCO com nome local diferente da confsib (situusu ≠ INATIVO), "
            "ou titular (codusu=00) com cadcont.nometit divergente do nomeusu local. "
            "O nome da cadusu já foi validado por humano na Receita Federal: "
            "manter cadusu.nomeusu (não acatar confsib) e enviar à ANS via SIB-FLEX "
            "para atualizar a confsib na próxima competência. "
            "Correção: ansnome=1, posans=10-SIB-FLEX; se titular, alinhar "
            "cadcont.nometit ao nomeusu local. "
            "Já preparados (ansnome=1 + 10-SIB-FLEX e nometit ok) saem da lista "
            "mesmo com divergência residual na confsib até o retorno ANS."
        ),
        expected_zero=True,
        count_sql=f"""
            SELECT COUNT(*) AS total FROM (
                SELECT DISTINCT ON (c.id) c.id
                FROM cadusu c
                INNER JOIN confsib s ON s.codcco = c.codcco
                LEFT JOIN cadcont ct ON ct.codtit = c.codtit
                WHERE {DIVERGENCIA_NOME_CADUSU_FILTRO}
                ORDER BY c.id, s.numseq DESC
            ) q
        """,
        detail_sql=f"""
            SELECT DISTINCT ON (c.id)
                   c.id, c.codtit, c.codusu, c.codcco, c.situusu, c.posans, c.ansnome,
                   c.nomeusu AS nome_local, s.nomeusu AS nome_ans,
                   ct.nometit AS nometit_contrato,
                   c.cpfusu, c.nascusu, c.dataini,
                   CASE
                     WHEN UPPER(TRIM(COALESCE(c.nomeusu, '')))
                          <> UPPER(TRIM(COALESCE(s.nomeusu, '')))
                       THEN 'enviar nome local a ANS (RF humano, SIB-FLEX)'
                     WHEN TRIM(c.codusu) = '00'
                          AND ct.codtit IS NOT NULL
                          AND UPPER(TRIM(COALESCE(ct.nometit, '')))
                              <> UPPER(TRIM(COALESCE(c.nomeusu, '')))
                       THEN 'alinhar nometit ao nome local (titular)'
                     ELSE 'ok'
                   END AS situacao_nome,
                   CASE
                     WHEN TRIM(c.codusu) = '00'
                          AND ct.codtit IS NOT NULL
                          AND UPPER(TRIM(COALESCE(ct.nometit, '')))
                              <> UPPER(TRIM(COALESCE(c.nomeusu, '')))
                       THEN 'atualizar nometit com nomeusu local'
                     WHEN TRIM(c.codusu) = '00'
                       THEN 'titular - nometit ok'
                     ELSE NULL
                   END AS situacao_titular
            FROM cadusu c
            INNER JOIN confsib s ON s.codcco = c.codcco
            LEFT JOIN cadcont ct ON ct.codtit = c.codtit
            WHERE {DIVERGENCIA_NOME_CADUSU_FILTRO}
            ORDER BY c.id, s.numseq DESC
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="divergencia_nome_inativo_confsib",
        category="Conferência ANS (confsib)",
        title="Divergência de nome (INATIVO) - acatar ANS",
        severity="media",
        description=(
            "Mesmo CODCCO com nome divergente e situusu = INATIVO. "
            "A base local acata o nome da ANS: atualiza cadusu.nomeusu com confsib.nomeusu."
        ),
        expected_zero=True,
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
        detail_sql=f"""
            SELECT DISTINCT ON (c.id)
                   c.id, c.codtit, c.codusu, c.codcco, c.situusu, c.posans,
                   c.nomeusu AS nome_local, s.nomeusu AS nome_ans,
                   c.cpfusu, c.nascusu, c.dataini
            FROM cadusu c
            INNER JOIN confsib s ON s.codcco = c.codcco
            WHERE COALESCE(c.codcco, '') <> ''
              AND c.situusu = 'INATIVO'
              AND UPPER(TRIM(COALESCE(c.nomeusu, '')))
                  <> UPPER(TRIM(COALESCE(s.nomeusu, '')))
              AND COALESCE(TRIM(s.nomeusu), '') <> ''
            ORDER BY c.id, s.numseq DESC
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="divergencia_nasc_cadusu_confsib",
        category="Conferência ANS (confsib)",
        title="Divergência de nascimento (não INATIVO) - enviar à ANS",
        severity="alta",
        description=(
            "Mesmo beneficiário (CODCCO + DATAINI + nome + CPF) com nascimento "
            "local diferente da confsib e situusu ≠ INATIVO. "
            "Enviar nascimento local à ANS via SIB-FLEX "
            "(posans = 10-SIB-FLEX e ansnasc = 1)."
        ),
        expected_zero=True,
        count_sql=f"""
            SELECT COUNT(DISTINCT c.id) AS total
            FROM cadusu c
            INNER JOIN confsib s ON s.codcco = c.codcco
            WHERE c.situusu <> 'INATIVO'
              AND ({MESMO_REGISTRO_CONFSIB})
              AND c.nascusu IS NOT NULL
              AND ({NASC_CONFSIB}) IS NOT NULL
              AND ({NASC_CONFSIB}) <> c.nascusu
              AND NOT (
                    c.posans = '10-SIB-FLEX'
                AND COALESCE(TRIM(c.ansnasc), '') = '1'
              )
        """,
        detail_sql=f"""
            SELECT DISTINCT ON (c.id)
                   c.id, c.codtit, c.codusu, c.codcco, c.situusu, c.posans, c.ansnasc,
                   c.nomeusu, c.cpfusu, c.dataini,
                   c.nascusu AS nasc_local,
                   ({NASC_CONFSIB}) AS nasc_ans,
                   s.nascusu AS nasc_ans_raw
            FROM cadusu c
            INNER JOIN confsib s ON s.codcco = c.codcco
            WHERE c.situusu <> 'INATIVO'
              AND ({MESMO_REGISTRO_CONFSIB})
              AND c.nascusu IS NOT NULL
              AND ({NASC_CONFSIB}) IS NOT NULL
              AND ({NASC_CONFSIB}) <> c.nascusu
              AND NOT (
                    c.posans = '10-SIB-FLEX'
                AND COALESCE(TRIM(c.ansnasc), '') = '1'
              )
            ORDER BY c.id, s.numseq DESC
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="sib_flex_sem_campo_marcado",
        category="POSANS / Situação",
        title="10-SIB-FLEX sem nenhum campo ANS marcado",
        severity="critica",
        description=(
            "POSANS 10-SIB-FLEX exige ao menos um flag ans* = '1'. "
            "Correção: comparar cadusu × confsib (mesmo CODCCO) e marcar com 1 "
            "cada flag cujo dado local diverge (ansrg←rgusu/docident, anscpf, "
            "ansmae, anscns, ansnasc, ansparentesco, ansnome, ansplano←codplano/"
            "codplaport|codplaope, ansdataini, ansdatafim). "
            "anstitular e anscnpjcei não têm espelho confiável na confsib "
            "(permanecem manuais se forem o caso)."
        ),
        expected_zero=True,
        count_sql=f"""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE posans = '10-SIB-FLEX'
              AND NOT ({ANS_FLEX_ALGUM_MARCADO})
        """,
        detail_sql=f"""
            SELECT c.id, c.codtit, c.codusu, c.nomeusu, c.situusu, c.posans,
                   c.codcco, c.codans, c.cpfusu, c.nascusu, c.dataini, c.datafim,
                   c.rgusu, c.mae, c.cns, c.parentesco, c.codplano,
                   {ANS_FLEX_COLS},
                   CASE WHEN s.codcco IS NULL THEN 'sem confsib'
                        WHEN ({SIB_FLEX_ALGUM_DIFF}) THEN 'com divergência'
                        ELSE 'sem divergência detectável'
                   END AS comparacao_ans
            FROM cadusu c
            LEFT JOIN LATERAL (
                SELECT s0.*
                FROM confsib s0
                WHERE s0.codcco = c.codcco
                ORDER BY s0.numseq DESC
                LIMIT 1
            ) s ON TRUE
            WHERE c.posans = '10-SIB-FLEX'
              AND NOT ({ANS_FLEX_ALGUM_MARCADO_C})
            ORDER BY c.codtit, c.codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="reativacao_cco_ja_ativo_confsib",
        category="Conferência ANS (confsib)",
        title="Reativação/reinclusão com CCO já ativo na confsib",
        severity="alta",
        description=(
            "POSANS 8-REINCLUSAO ou 9-RET REATIV com o mesmo CCO já ATIVO na "
            "confsib (status=A). A ANS rejeita reativação ('CCO já ativo'). "
            "Não enviar 8/9: alinhar a base local ao estado da ANS "
            "(situusu = ATIVO, posans = 4-ATUALIZADO, datafim limpa). "
            "Se a intenção for excluir quem ainda está ativo na ANS, use a regra "
            "'Inativo na cadusu e ativo na confsib' (3-EXCLUSAO), não reativação."
        ),
        expected_zero=True,
        count_sql=f"""
            SELECT COUNT(*) AS total
            FROM cadusu c
            INNER JOIN (
                {CONFSIB_LATEST_BY_CCO}
            ) s ON s.codcco = c.codcco
            WHERE c.posans IN ('8-REINCLUSAO', '9-RET REATIV')
              AND COALESCE(TRIM(c.codcco), '') <> ''
              AND TRIM(s.status) = 'A'
        """,
        detail_sql=f"""
            SELECT c.id, c.codtit, c.codusu, c.nomeusu, c.situusu, c.posans,
                   c.codcco, c.codans, c.cpfusu, c.nascusu, c.dataini, c.datafim,
                   s.status AS status_ans, s.nomeusu AS nome_ans,
                   s.dataini AS dataini_ans,
                   'CCO ja ativo na ANS - nao enviar reativacao/reinclusao'::text
                     AS situacao_reativacao
            FROM cadusu c
            INNER JOIN (
                {CONFSIB_LATEST_BY_CCO}
            ) s ON s.codcco = c.codcco
            WHERE c.posans IN ('8-REINCLUSAO', '9-RET REATIV')
              AND COALESCE(TRIM(c.codcco), '') <> ''
              AND TRIM(s.status) = 'A'
            ORDER BY c.posans, c.situusu, c.codtit, c.codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="ret_reativ_com_cco",
        category="POSANS / Situação",
        title="9-RET REATIV com CCO e situação ≠ INATIVO",
        severity="alta",
        description=(
            "POSANS 9-RET REATIV com CODCCO informado e situusu diferente de INATIVO "
            "indica reativação já refletida na ANS. Ajuste correto: posans = 4-ATUALIZADO."
        ),
        expected_zero=True,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE posans = '9-RET REATIV'
              AND situusu <> 'INATIVO'
              AND COALESCE(TRIM(codcco), '') <> ''
        """,
        detail_sql=f"""
            SELECT {CADUSU_COLS} FROM cadusu
            WHERE posans = '9-RET REATIV'
              AND situusu <> 'INATIVO'
              AND COALESCE(TRIM(codcco), '') <> ''
            ORDER BY situusu, codtit, codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="posans_desconhecido",
        category="Integridade",
        title="POSANS fora do domínio conhecido",
        severity="media",
        description=(
            "Valores de POSANS diferentes de 1-INCLUSAO, 2-ALTERACAO, 3-EXCLUSAO, "
            "4-ATUALIZADO, 8-REINCLUSAO, 9-RET REATIV e 10-SIB-FLEX indicam dado "
            "corrompido ou legado não mapeado."
        ),
        expected_zero=True,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE posans NOT IN (
                '1-INCLUSAO', '2-ALTERACAO', '3-EXCLUSAO',
                '4-ATUALIZADO', '8-REINCLUSAO', '9-RET REATIV', '10-SIB-FLEX'
            )
        """,
        detail_sql=f"""
            SELECT {CADUSU_COLS} FROM cadusu
            WHERE posans NOT IN (
                '1-INCLUSAO', '2-ALTERACAO', '3-EXCLUSAO',
                '4-ATUALIZADO', '8-REINCLUSAO', '9-RET REATIV', '10-SIB-FLEX'
            )
            ORDER BY posans, codtit, codusu
            {_limit_clause()}
        """,
    ),
]


_RULES_BY_ID: dict[str, SibRule] = {r.id: r for r in RULES}


def list_rules() -> list[dict[str, Any]]:
    from validators.corrections import fix_meta

    return [
        {
            "id": r.id,
            "category": r.category,
            "title": r.title,
            "severity": r.severity,
            "description": r.description,
            "expected_zero": r.expected_zero,
            **fix_meta(r.id),
        }
        for r in RULES
    ]


def get_rule(rule_id: str) -> SibRule | None:
    return _RULES_BY_ID.get(rule_id)


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _with_critica_dataini_order(detail_sql: str) -> str:
    """Reordena detalhe de regras críticas por dataini da cadusu (mais recente primeiro)."""
    stripped = re.sub(
        r"\s+LIMIT\s+\d+\s*$",
        "",
        detail_sql.strip(),
        flags=re.IGNORECASE,
    )
    return f"""
            SELECT * FROM (
                {stripped}
            ) _crit_ord
            ORDER BY _crit_ord.dataini DESC NULLS LAST
            {_limit_clause()}
        """


def summarize_all() -> list[dict[str, Any]]:
    result = []
    for rule in RULES:
        try:
            total = fetch_count(_resolve_sql(rule.count_sql))
            error = None
        except Exception as exc:
            total = -1
            error = str(exc)
        result.append(
            {
                "id": rule.id,
                "category": rule.category,
                "title": rule.title,
                "severity": rule.severity,
                "description": rule.description,
                "expected_zero": rule.expected_zero,
                "total": total,
                "ok": total == 0 if total >= 0 else False,
                "error": error,
            }
        )
    return result


def count_rule(rule_id: str) -> dict[str, Any]:
    rule = get_rule(rule_id)
    if not rule:
        raise KeyError(f"Regra não encontrada: {rule_id}")
    total = fetch_count(_resolve_sql(rule.count_sql))
    return {
        "id": rule.id,
        "category": rule.category,
        "title": rule.title,
        "severity": rule.severity,
        "description": rule.description,
        "expected_zero": rule.expected_zero,
        "total": total,
        "ok": total == 0,
        "error": None,
    }


def detail_rule(rule_id: str) -> dict[str, Any]:
    rule = get_rule(rule_id)
    if not rule:
        raise KeyError(f"Regra não encontrada: {rule_id}")
    detail_sql = _resolve_sql(rule.detail_sql)
    already_ordered = "dataini desc" in detail_sql.lower()
    if (
        rule.severity == "critica"
        and "dataini" in detail_sql.lower()
        and not already_ordered
    ):
        detail_sql = _with_critica_dataini_order(detail_sql)
    rows = fetch_all(detail_sql)
    # Evita 2a passagem pesada no count quando o detalhe ja trouxe todos.
    if len(rows) < Config.MAX_ROWS:
        total = len(rows)
        truncated = False
    else:
        total = fetch_count(_resolve_sql(rule.count_sql))
        truncated = total > len(rows)
    return {
        "id": rule.id,
        "category": rule.category,
        "title": rule.title,
        "severity": rule.severity,
        "description": rule.description,
        "expected_zero": rule.expected_zero,
        "total": total,
        "returned": len(rows),
        "truncated": truncated,
        "max_rows": Config.MAX_ROWS,
        "columns": list(rows[0].keys()) if rows else [],
        "rows": [_serialize_row(r) for r in rows],
        "ok": total == 0,
    }


def dashboard_totals() -> dict[str, Any]:
    cadusu = fetch_count("SELECT COUNT(*) AS total FROM cadusu")
    confsib = fetch_count("SELECT COUNT(*) AS total FROM confsib")
    ativos = fetch_count("SELECT COUNT(*) AS total FROM cadusu WHERE situusu = 'ATIVO'")
    inativos = fetch_count("SELECT COUNT(*) AS total FROM cadusu WHERE situusu = 'INATIVO'")
    return {
        "cadusu": cadusu,
        "confsib": confsib,
        "ativos": ativos,
        "inativos": inativos,
    }
