from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `messages` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(50) NOT NULL,
    `content` LONGTEXT NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `aerich` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `version` VARCHAR(255) NOT NULL,
    `app` VARCHAR(100) NOT NULL,
    `content` JSON NOT NULL
) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """


MODELS_STATE = (
    "eJztll1v2jAUhv9KlCsmdRXNoK12l1G2MhWY2myrWlWRiU2wSOw0dlpQxX+fj5OQDyACad"
    "KKtCuS97y2z3lifPxmhhyTQJwOiRDIJ+Zn481kKISHeujEMFEUFQEQJJoEqTc1aRFNhIyR"
    "J5U+RYEgSsJEeDGNJOVMqSwJAhC5p4yU+YWUMPqcEFdyn8gZiVXg8UnJlGGyUJNnr9HcnV"
    "IS4Eq2FMPaWnflMtLagMmv2girTVyPB0nICnO0lDPO1m7KJKg+YSRGksD0Mk4gfcguqzSv"
    "KM20sKQplsZgMkVJIEvl7snA4wz4qWyELlB/lY/WWeeic/npvHOpLDqTtXKxSssrak8Hag"
    "Ijx1zpOJIodWiMBTf9u0GuN0PxdnS5vwZPpVyHl6NqopcLBb5iy/wlfiFauAFhvpyp1267"
    "AdYv+7Z3bd+2uu0PUAtXmzjd3aMsYukQ8Cz4qeUkSXdOFaFDFjt2X2nIsVBsoOb07x1IOh"
    "TiOSjTag3tew0yXGaRm/HoW24v0e3djL/UqcYE6nfRFrBXKiJpSHbArYys8cXZ0NP84X3S"
    "NlUNeMyCZXacNNEfDPt3jj38UfkEV7bTh4hVwZ+rrfPa/l5PYvweONcGvBoP41FfE+RC+r"
    "FesfA5DybkhBLJXcZfXYRLJ1+u5mBWcGZP56XTB4QJ8uavKMbuRoRbfJd3MxRaYV1BTHUi"
    "nMGFNLNGZpOYerNtLS6LNHY4VHj+97cj6m8vJBaQ0gEtrjTkWM7napezut092pxy7exzOl"
    "Y9kuGvcQDEzH6cAM/a+9wTlGsnQB3b86bw/W48OvSm8JOpAh8x9eSJEVAhn94n1gaKUHXz"
    "vaF+Rah1I5gA7g3/tL2s/gABWDlQ"
)
