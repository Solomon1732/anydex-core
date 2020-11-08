"""
This file contains everything related to persistence for the market community.
"""
from os import path

from ipv8.database import database_blob

from anydex.core.message import TraderId
from anydex.core.order import Order, OrderId, OrderNumber
from anydex.core.payment import Payment
from anydex.core.tick import Tick
from anydex.core.transaction import Transaction, TransactionId
from anydex.trustchain.database import TrustChainDB


DATABASE_DIRECTORY = path.join(u"sqlite")
# Path to the database location + dispersy._workingdirectory
DATABASE_PATH = path.join(DATABASE_DIRECTORY, u"market.db")
# Version to keep track if the db schema needs to be updated.
LATEST_DB_VERSION = 5
# Schema for the Market DB.
schema = u"""
CREATE TABLE IF NOT EXISTS orders(
 trader_id            TEXT NOT NULL,
 order_number         INTEGER NOT NULL,
 asset1_amount        BIGINT NOT NULL,
 asset1_type          TEXT NOT NULL,
 asset2_amount        BIGINT NOT NULL,
 asset2_type          TEXT NOT NULL,
 traded_quantity      BIGINT NOT NULL,
 received_quantity    BIGINT NOT NULL,
 timeout              INTEGER NOT NULL,
 order_timestamp      BIGINT NOT NULL,
 completed_timestamp  BIGINT,
 is_ask               INTEGER NOT NULL,
 cancelled            INTEGER NOT NULL,
 verified             INTEGER NOT NULL,

 PRIMARY KEY (trader_id, order_number)
 );

 CREATE TABLE IF NOT EXISTS transactions(
  trader_id                TEXT NOT NULL,
  transaction_id           TEXT NOT NULL,
  order_number             INTEGER NOT NULL,
  partner_trader_id        TEXT NOT NULL,
  partner_order_number     INTEGER NOT NULL,
  asset1_amount            BIGINT NOT NULL,
  asset1_type              TEXT NOT NULL,
  asset1_transferred       BIGINT NOT NULL,
  asset2_amount            BIGINT NOT NULL,
  asset2_type              TEXT NOT NULL,
  asset2_transferred       BIGINT NOT NULL,
  transaction_timestamp    BIGINT NOT NULL,
  sent_wallet_info         INTEGER NOT NULL,
  received_wallet_info     INTEGER NOT NULL,
  incoming_address         TEXT NOT NULL,
  outgoing_address         TEXT NOT NULL,
  partner_incoming_address TEXT NOT NULL,
  partner_outgoing_address TEXT NOT NULL,

  PRIMARY KEY (transaction_id)
 );

 CREATE TABLE IF NOT EXISTS payments(
  trader_id                TEXT NOT NULL,
  transaction_id           TEXT NOT NULL,
  payment_id               TEXT NOT NULL,
  transferred_amount       BIGINT NOT NULL,
  transferred_type         TEXT NOT NULL,
  address_from             TEXT NOT NULL,
  address_to               TEXT NOT NULL,
  timestamp                BIGINT NOT NULL,

  PRIMARY KEY (trader_id, payment_id, transaction_id)
 );

 CREATE TABLE IF NOT EXISTS ticks(
  trader_id            TEXT NOT NULL,
  order_number         INTEGER NOT NULL,
  asset1_amount        BIGINT NOT NULL,
  asset1_type          TEXT NOT NULL,
  asset2_amount        BIGINT NOT NULL,
  asset2_type          TEXT NOT NULL,
  timeout              INTEGER NOT NULL,
  timestamp            BIGINT NOT NULL,
  is_ask               INTEGER NOT NULL,
  traded               BIGINT NOT NULL,
  block_hash           TEXT NOT NULL,

  PRIMARY KEY (trader_id, order_number)
 );

 CREATE TABLE IF NOT EXISTS orders_reserved_ticks(
  trader_id              TEXT NOT NULL,
  order_number           INTEGER NOT NULL,
  reserved_trader_id     TEXT NOT NULL,
  reserved_order_number  INTEGER NOT NULL,
  quantity               BIGINT NOT NULL,

  PRIMARY KEY (trader_id, order_number, reserved_trader_id, reserved_order_number)
 );

CREATE TABLE IF NOT EXISTS option(key TEXT PRIMARY KEY, value BLOB);
INSERT OR REPLACE INTO option(key, value) VALUES('database_version', '""" + str(LATEST_DB_VERSION) + u"""');
"""


class MarketDB(TrustChainDB):
    """
    Persistence layer for the Market Community.
    Connection layer to SQLiteDB.
    Ensures a proper DB schema on startup.
    """

    def get_schema(self):
        """
        Return the schema for the database.
        """
        return schema

    def get_all_orders(self):
        """
        Return all orders in the database.
        """
        db_result = self.execute(u"SELECT * FROM orders")
        return [Order.from_database(db_item, self.get_reserved_ticks(
            OrderId(TraderId(bytes(db_item[0])), OrderNumber(db_item[1])))) for db_item in db_result]

    def get_order(self, order_id):
        """
        Return an order with a specific id.
        """
        try:
            db_result = next(self.execute(u"SELECT * FROM orders WHERE trader_id = ? AND order_number = ?",
                                          (database_blob(bytes(order_id.trader_id)),
                                           str(order_id.order_number))))
        except StopIteration:
            return None
        return Order.from_database(db_result, self.get_reserved_ticks(order_id))

    def add_order(self, order):
        """
        Add a specific order to the database
        """
        self.execute(
            u"INSERT INTO orders (trader_id, order_number, asset1_amount, asset1_type, asset2_amount, asset2_type,"
            u"traded_quantity, received_quantity, timeout, order_timestamp, completed_timestamp, is_ask, cancelled,"
            u"verified) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            order.to_database())
        self.commit()

        # Add reserved ticks
        for reserved_order_id, quantity in order.reserved_ticks.items():
            self.add_reserved_tick(order.order_id, reserved_order_id, quantity)

    def delete_order(self, order_id):
        """
        Delete a specific order from the database
        """
        self.execute(u"DELETE FROM orders WHERE trader_id = ? AND order_number = ?",
                     (database_blob(bytes(order_id.trader_id)), str(order_id.order_number)))
        self.delete_reserved_ticks(order_id)

    def get_next_order_number(self):
        """
        Return the next order number from the database
        """
        highest_order_number = next(self.execute(u"SELECT MAX(order_number) FROM orders"))
        if not highest_order_number[0]:
            return 1
        return highest_order_number[0] + 1

    def delete_reserved_ticks(self, order_id):
        """
        Delete all reserved ticks from a specific order
        """
        self.execute(u"DELETE FROM orders_reserved_ticks WHERE trader_id = ? AND order_number = ?",
                     (database_blob(bytes(order_id.trader_id)), str(order_id.order_number)))

    def add_reserved_tick(self, order_id, reserved_order_id, amount):
        """
        Add a reserved tick to the database
        """
        self.execute(
            u"INSERT INTO orders_reserved_ticks (trader_id, order_number, reserved_trader_id, reserved_order_number,"
            u"quantity) VALUES(?,?,?,?,?)",
            (database_blob(bytes(order_id.trader_id)), str(order_id.order_number),
             database_blob(bytes(reserved_order_id.trader_id)), str(reserved_order_id.order_number), amount))
        self.commit()

    def get_reserved_ticks(self, order_id):
        """
        Get all reserved ticks for a specific order.
        """
        db_results = self.execute(u"SELECT * FROM orders_reserved_ticks WHERE trader_id = ? AND order_number = ?",
                                  (database_blob(bytes(order_id.trader_id)), str(order_id.order_number)))
        return [(OrderId(TraderId(bytes(data[2])), OrderNumber(data[3])), data[4]) for data in db_results]

    def get_all_transactions(self):
        """
        Return all transactions in the database.
        """
        db_result = self.execute(u"SELECT * FROM transactions")
        return [Transaction.from_database(db_item,
                                          self.get_payments(TransactionId(db_item[1])))
                for db_item in db_result]

    def get_transaction(self, transaction_id):
        """
        Return a transaction with a specific id.
        """
        try:
            db_result = next(self.execute(u"SELECT * FROM transactions WHERE transaction_id = ?",
                                          (database_blob(bytes(transaction_id)),)))
        except StopIteration:
            return None
        return Transaction.from_database(db_result, self.get_payments(transaction_id))

    def add_transaction(self, transaction):
        """
        Add a specific transaction to the database
        """
        self.execute(
            u"INSERT INTO transactions (trader_id, transaction_id, order_number,"
            u"partner_trader_id, partner_order_number, asset1_amount, asset1_type, asset1_transferred, asset2_amount,"
            u"asset2_type, asset2_transferred, transaction_timestamp, sent_wallet_info, received_wallet_info,"
            u"incoming_address, outgoing_address, partner_incoming_address, partner_outgoing_address) "
            u"VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", transaction.to_database())
        self.commit()

        self.delete_payments(transaction.transaction_id)
        for payment in transaction.payments:
            self.add_payment(payment)

    def insert_or_update_transaction(self, transaction):
        """
        Inserts or updates a specific transaction in the database, according to the timestamp.
        Updates only if the timestamp is more recent than the one in the database.
        """
        self.execute(
            u"INSERT OR IGNORE INTO transactions (trader_id, transaction_id, order_number,"
            u"partner_trader_id, partner_order_number, asset1_amount, asset1_type, asset1_transferred, asset2_amount,"
            u"asset2_type, asset2_transferred, transaction_timestamp, sent_wallet_info, received_wallet_info,"
            u"incoming_address, outgoing_address, partner_incoming_address, partner_outgoing_address) "
            u"VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", transaction.to_database())

        self.execute(
            u"UPDATE transactions SET asset1_amount = ?, asset1_transferred = ?, asset2_amount = ?, "
            u"asset2_transferred = ?, transaction_timestamp = ? WHERE transaction_id = ?"
            u"AND transaction_timestamp < ?", (transaction.assets.first.amount,
                                               transaction.transferred_assets.first.amount,
                                               transaction.assets.second.amount,
                                               transaction.transferred_assets.second.amount,
                                               int(transaction.timestamp),
                                               database_blob(bytes(transaction.transaction_id)),
                                               int(transaction.timestamp))
        )

        self.commit()

    def delete_transaction(self, transaction_id):
        """
        Delete a specific transaction from the database
        """
        self.execute(u"DELETE FROM transactions WHERE transaction_id = ?", (database_blob(bytes(transaction_id)),))
        self.delete_payments(transaction_id)

    def add_payment(self, payment):
        """
        Add a specific transaction to the database
        """
        self.execute(
            u"INSERT INTO payments (trader_id, transaction_id, payment_id,"
            u"transferred_amount, transferred_type, address_from, address_to, timestamp) VALUES(?,?,?,?,?,?,?,?)",
            payment.to_database())
        self.commit()

    def get_payments(self, transaction_id):
        """
        Return all payment tied to a specific transaction.
        """
        db_result = self.execute(u"SELECT * FROM payments WHERE transaction_id = ? ORDER BY timestamp ASC",
                                 (database_blob(bytes(transaction_id)),))
        return [Payment.from_database(db_item) for db_item in db_result]

    def delete_payments(self, transaction_id):
        """
        Delete all payments that are associated with a specific transaction
        """
        self.execute(u"DELETE FROM payments WHERE transaction_id = ?", (database_blob(bytes(transaction_id)), ))

    def add_tick(self, tick):
        """
        Add a specific tick to the database
        """
        self.execute(
            u"INSERT INTO ticks (trader_id, order_number, asset1_amount, asset1_type, asset2_amount,"
            u"asset2_type, timeout, timestamp, is_ask, traded, block_hash) "
            u"VALUES(?,?,?,?,?,?,?,?,?,?,?)", tick.to_database())
        self.commit()

    def delete_all_ticks(self):
        """
        Remove all ticks from the database.
        """
        self.execute(u"DELETE FROM ticks")

    def get_ticks(self):
        """
        Get all ticks present in the database.
        """
        return [Tick.from_database(db_tick) for db_tick in self.execute(u"SELECT * FROM ticks")]

    def open(self, initial_statements=True, prepare_visioning=True):
        return super(MarketDB, self).open(initial_statements, prepare_visioning)

    def get_upgrade_script(self, current_version):
        if current_version == 1 or current_version == 2 or current_version == 3 or current_version == 4:
            return u"DROP TABLE IF EXISTS orders;" \
                   u"DROP TABLE IF EXISTS transactions;" \
                   u"DROP TABLE IF EXISTS payments;" \
                   u"DROP TABLE IF EXISTS ticks;" \
                   u"DROP TABLE IF EXISTS orders_reserved_ticks;" \
                   u"DROP TABLE IF EXISTS option;" \
                   u"DROP TABLE IF EXISTS traders;"

    def check_database(self, database_version):
        """
        Ensure the proper schema is used by the database.
        :param database_version: Current version of the database.
        :return:
        """
        assert isinstance(database_version, bytes)
        assert database_version.isdigit()
        assert int(database_version) >= 0
        database_version = int(database_version)

        if database_version < self.LATEST_DB_VERSION:
            while database_version < LATEST_DB_VERSION:
                upgrade_script = self.get_upgrade_script(current_version=database_version)
                if upgrade_script:
                    self.executescript(upgrade_script)
                database_version += 1
            self.executescript(self.get_schema())
            self.commit()

        return LATEST_DB_VERSION
