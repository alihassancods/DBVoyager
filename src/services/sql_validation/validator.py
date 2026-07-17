FORBIDDEN_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "GRANT",
    "REVOKE",
    "MERGE",
}


def SQLValidator(sql: str) -> bool:
    """
    Only read queries are allowed.
    """

    sql_upper = sql.upper()

    if not sql_upper.startswith("SELECT"):
        return False

    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in sql_upper:
            return False

    return True