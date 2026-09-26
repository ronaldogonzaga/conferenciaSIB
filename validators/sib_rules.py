from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
ANS_FLEX_COLS = ", ".join(ANS_FLEX_FLAGS)


@dataclass(frozen=True)
class SibRule:
    id: str
    category: str
    title: str
    severity: str
    description: str
    expected_zero: bool
    count_sql: str
    detail_sql: str


def _limit_clause() -> str:
    return f" LIMIT {Config.MAX_ROWS}"


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
            "não conciliado após envio/retorno ANS — devem ser zerados após acerto."
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
            "indica reinclusão travada — prazo operacional extrapolado."
        ),
        expected_zero=True,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE dataini < CURRENT_DATE - INTERVAL '90 days'
              AND posans = '8-REINCLUSAO'
              AND COALESCE(TRIM(codcco), '') <> ''
        """,
        detail_sql=f"""
            SELECT {CADUSU_COLS} FROM cadusu
            WHERE dataini < CURRENT_DATE - INTERVAL '90 days'
              AND posans = '8-REINCLUSAO'
              AND COALESCE(TRIM(codcco), '') <> ''
            ORDER BY dataini, codtit, codusu
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
            "não deveria persistir — a inclusão já deveria ter virado 4-ATUALIZADO."
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
        title="Registro na confsib sem correspondente em cadusu",
        severity="alta",
        description=(
            "Beneficiário presente no retorno ANS (confsib) sem vínculo local em cadusu. "
            "Chaves: 1) CODCCO; 2) CODUSU=CODANS + nascimento; 3) CPF + nascimento."
        ),
        expected_zero=True,
        count_sql=f"""
            SELECT COUNT(*) AS total
            FROM confsib s
            WHERE NOT EXISTS (
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
        """,
        detail_sql=f"""
            SELECT s.numseq, s.status, s.codcco, s.codusu, s.nomeusu, s.cpfusu,
                   s.nascusu, s.sexousu, s.dataini, s.datafim, s.flag, s.registro
            FROM confsib s
            WHERE NOT EXISTS (
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
            ORDER BY s.nomeusu NULLS LAST, s.numseq
            {_limit_clause()}
        """,
    ),


    SibRule(
        id="ativo_sem_cco_fora_inclusao",
        category="POSANS / Situação",
        title="Ativo sem CCO fora de inclusão/reinclusão",
        severity="critica",
        description=(
            "Beneficiário ATIVO sem CODCCO e com CPF deve estar em 1-INCLUSAO ou 8-REINCLUSAO. "
            "Sem CPF não se envia inclusão à ANS (não atribui CCO); esses casos são tratados "
            "na regra 'Ativo sem CPF' (posans = 4-ATUALIZADO)."
        ),
        expected_zero=True,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE situusu = 'ATIVO'
              AND COALESCE(TRIM(codcco), '') = ''
              AND COALESCE(TRIM(cpfusu), '') <> ''
              AND posans NOT IN ('1-INCLUSAO', '8-REINCLUSAO')
        """,
        detail_sql=f"""
            SELECT {CADUSU_COLS} FROM cadusu
            WHERE situusu = 'ATIVO'
              AND COALESCE(TRIM(codcco), '') = ''
              AND COALESCE(TRIM(cpfusu), '') <> ''
              AND posans NOT IN ('1-INCLUSAO', '8-REINCLUSAO')
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
            "(já excluído/conciliado na ANS). Outros POSANS geram divergência no SIB."
        ),
        expected_zero=True,
        count_sql="""
            SELECT COUNT(*) AS total FROM cadusu
            WHERE situusu = 'INATIVO'
              AND COALESCE(TRIM(codcco), '') <> ''
              AND posans NOT IN ('3-EXCLUSAO', '4-ATUALIZADO')
        """,
        detail_sql=f"""
            SELECT {CADUSU_COLS} FROM cadusu
            WHERE situusu = 'INATIVO'
              AND COALESCE(TRIM(codcco), '') <> ''
              AND posans NOT IN ('3-EXCLUSAO', '4-ATUALIZADO')
            ORDER BY posans, datafim NULLS LAST, codtit, codusu
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="exclusao_sem_datafim",
        category="Datas obrigatórias",
        title="Exclusão sem data de fim (DATAFIM) — INATIVO",
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
        title="3-EXCLUSAO com situusu ≠ INATIVO — ajustar POSANS",
        severity="alta",
        description=(
            "POSANS 3-EXCLUSAO com situusu ≠ INATIVO (ex.: BLOQUEADO) e CODCCO válido: "
            "erro de cadastro — usuário bloqueou o beneficiário e setou 3-EXCLUSAO "
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
            "Não usar 1-INCLUSAO sem CPF — a ANS não acata o cadastro para atribuir CCO."
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
        id="cpf_duplicado_ativos",
        category="Integridade",
        title="CPF duplicado entre ATIVOS na mesma empresa",
        severity="alta",
        description=(
            "Dois ou mais ATIVOS com o mesmo CPF na mesma empresa "
            "(4 primeiros dígitos de CODTIT). CPF repetido em empresas "
            "diferentes é permitido."
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
            "ou cadastrado em pessoas distintas — exige correção prioritária."
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
                SELECT id, codtit, codusu, nomeusu, cpfusu, nascusu,
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
                   b.codcco, b.posans,
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
        title="Divergência de nome (não INATIVO) — enviar à ANS",
        severity="media",
        description=(
            "Mesmo CODCCO com nome local diferente do retorno ANS e situusu ≠ INATIVO. "
            "Enviar nome local à ANS via SIB-FLEX "
            "(posans = 10-SIB-FLEX e ansnome = 1), qualquer codusu."
        ),
        expected_zero=True,
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
        detail_sql=f"""
            SELECT DISTINCT ON (c.id)
                   c.id, c.codtit, c.codusu, c.codcco, c.situusu, c.posans, c.ansnome,
                   c.nomeusu AS nome_local, s.nomeusu AS nome_ans,
                   c.cpfusu, c.nascusu, c.dataini
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
            {_limit_clause()}
        """,
    ),
    SibRule(
        id="divergencia_nome_inativo_confsib",
        category="Conferência ANS (confsib)",
        title="Divergência de nome (INATIVO) — acatar ANS",
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
        title="Divergência de nascimento (não INATIVO) — enviar à ANS",
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


def summarize_all() -> list[dict[str, Any]]:
    result = []
    for rule in RULES:
        try:
            total = fetch_count(rule.count_sql)
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
    total = fetch_count(rule.count_sql)
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
    total = fetch_count(rule.count_sql)
    rows = fetch_all(rule.detail_sql)
    return {
        "id": rule.id,
        "category": rule.category,
        "title": rule.title,
        "severity": rule.severity,
        "description": rule.description,
        "expected_zero": rule.expected_zero,
        "total": total,
        "returned": len(rows),
        "truncated": total > len(rows),
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
