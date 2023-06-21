#!/usr/bin/env python3
# Copyright (c) 2019-2020 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test signature independent merkle root signet functionality"""
import time
import sys, os

# Import the test primitives
from test_framework.messages import COIN, COutPoint, CTransaction, CTxIn, CTxOut, tx_from_hex
from test_framework.test_framework_itcoin import BaseItcoinTest
from test_framework.util import assert_equal

# import itcoin's miner
from test_framework.itcoin_abs_import import import_miner
miner = import_miner()

class SignetSignatureIndependentMerkleRootTest(BaseItcoinTest):

    def set_test_params(self):
        self.num_nodes = 2
        self.signet_num_signers = 2
        self.signet_num_signatures = 1
        super().set_test_params()

    def run_test(self):
        self.log.info("Tests using 1-of-2 challenge")

        signet_challenge = self.signet_challenge
        args0 = self.node(0).args
        args1 = self.node(1).args

        # Test initial state
        self.assert_blockchaininfo_property_forall_nodes("blocks", 0)

        # Generate the first block
        # Mine 1st block
        block = miner.do_generate_next_block(args0)[0]
        signed_block = miner.do_sign_block(args0, block, signet_challenge)
        miner.do_propagate_block(args0, signed_block)
        self.sync_all(self.nodes[0:2])

        # Check 1st block mined correctly on node 0
        self.assert_blockchaininfo_property(0, "blocks", 1)

        # Check that 1st block propagates correctly to node 1
        self.assert_blockchaininfo_property(1, "blocks", 1)

        # Mine 2nd block
        block = miner.do_generate_next_block(args0)[0]
        signed_block = miner.do_sign_block(args0, block, signet_challenge)
        miner.do_propagate_block(args0, signed_block)
        self.sync_all(self.nodes[0:2])

        # Check 2nd block mined correctly on node 0
        self.assert_blockchaininfo_property(0, "blocks", 2)

        # Check that 2nd block propagates correctly to node 1
        self.assert_blockchaininfo_property(1, "blocks", 2)

        # 3rd block, we try to cause a fork based on different signatures.
        self.disconnect_nodes(0, 1)

        # Node 0 generates the block
        block = miner.do_generate_next_block(args0)[0]

        # Block signed by node 0
        signed_block_0 = miner.do_sign_block(args0, block, signet_challenge)
        miner.do_propagate_block(args0, signed_block_0)

        # Block signed by node 1
        signed_block_1 = miner.do_sign_block(args1, block, signet_challenge)
        miner.do_propagate_block(args1, signed_block_1)

        # Check block hashes of different nodes
        self.assert_blockchaininfo_property_forall_nodes("blocks", 3)

        # Assert the block hashes are the same
        expected_bestblockhash = self.get_blockchaininfo_field_from_node(0, "bestblockhash")
        self.assert_blockchaininfo_property_forall_nodes("bestblockhash", expected_bestblockhash)

        # Save best block hash of nodes during the partition
        bestblockhash_before_connect = expected_bestblockhash

        # Reconnect the nodes
        self.connect_nodes(0, 1)
        self.sync_all(self.nodes[0:2])

        # Check they are at the same height
        self.assert_blockchaininfo_property_forall_nodes("blocks", 3)
        expected_bestblockhash = self.get_blockchaininfo_field_from_node(0, "bestblockhash")
        self.assert_blockchaininfo_property_forall_nodes("bestblockhash", expected_bestblockhash)

        # Check a reorg did not occurr after the partition is resolved
        assert_equal(expected_bestblockhash, bestblockhash_before_connect)

        #  but they kept the same different coinbase txs
        block3_coinbase_0 = self.nodes[0].getblock(self.nodes[0].getblockhash(3))["tx"][0]
        block3_coinbase_1 = self.nodes[1].getblock(self.nodes[1].getblockhash(3))["tx"][0]
        # The hash of the coinbase should be the same
        assert_equal(block3_coinbase_0, block3_coinbase_1)
        # The content of the coinbase should be different
        block3_hash = self.nodes[0].getblockhash(3)
        raw_tx_block3_coinbase_0 = self.nodes[0].getrawtransaction(block3_coinbase_0, True, block3_hash)["hex"]
        raw_tx_block3_coinbase_1 = self.nodes[1].getrawtransaction(block3_coinbase_1, True, block3_hash)["hex"]
        assert(raw_tx_block3_coinbase_0 != raw_tx_block3_coinbase_1)
        # The content of the coinbase, once excluded the signet solution, should be the same
        tx_block3_coinbase_0 = tx_from_hex(raw_tx_block3_coinbase_0)
        tx_block3_coinbase_1 = tx_from_hex(raw_tx_block3_coinbase_1)
        # To exclude the signet solution, take the first 38 bytes of the 2nd coinbase output
        #   01 byte contains OP_RETURN (=6a hex) 
        # + 01 byte contains the size of the PUSH_DATA (=24 hex) 
        # + 04 bytes contain the WITNESS_COMMITMENT_HEADER (=aa21a9ed hex)
        # + 32 bytes contain the witness commitment (sha256 of the segwit merkle root)
        # = 38 bytes
        tx_block3_coinbase_0.vout[1].scriptPubKey = tx_block3_coinbase_0.vout[1].scriptPubKey[:38]
        tx_block3_coinbase_1.vout[1].scriptPubKey = tx_block3_coinbase_1.vout[1].scriptPubKey[:38]
        assert_equal(tx_block3_coinbase_0.serialize().hex(), tx_block3_coinbase_1.serialize().hex())

        # Mine 4th block
        block = miner.do_generate_next_block(args0)[0]
        signed_block = miner.do_sign_block(args0, block, signet_challenge)
        miner.do_propagate_block(args0, signed_block)
        self.sync_all(self.nodes[0:2])

        # Check 4th block mined correctly on node 0
        self.assert_blockchaininfo_property(0, "blocks", 4)

        # Check that 4th block propagates correctly to node 1
        self.assert_blockchaininfo_property(1, "blocks", 4)

        # Assert the two chains are in sync even if each node kept its own
        # original coinbase transaction
        expected_bestblockhash = self.get_blockchaininfo_field_from_node(0, "bestblockhash")
        self.assert_blockchaininfo_property_forall_nodes('bestblockhash', expected_bestblockhash)
        raw_tx_block3_coinbase_0_new = self.nodes[0].getrawtransaction(block3_coinbase_0, True, block3_hash)["hex"]
        raw_tx_block3_coinbase_1_new = self.nodes[1].getrawtransaction(block3_coinbase_1, True, block3_hash)["hex"]
        assert_equal(raw_tx_block3_coinbase_0, raw_tx_block3_coinbase_0_new)
        assert_equal(raw_tx_block3_coinbase_1, raw_tx_block3_coinbase_1_new)

        # Spend block3_coinbase_0 at node 1
        #
        # Since block3_coinbase_0 and block3_coinbase_1 are the same hash:
        # - Node 0 will submit the spending transaction, and will propagate it
        #   to Node 1.
        # - Node 1 will accept the spending transaction coming from node 0, and
        #   will add it to its mempool.
        # - Later, when Node 1 tries to add the transaction to its mempool
        #   again, txn-already-in-mempool is raised.

        # Prepare the transaction
        destination_address_0 = self.nodes[0].getnewaddress()
        destination_scriptpubkey_0 = bytes.fromhex(self.nodes[0].validateaddress(destination_address_0)['scriptPubKey'])
        coinbase_spending_tx = CTransaction()
        coinbase_spending_tx.vin = [CTxIn(COutPoint(int(block3_coinbase_0, 16), 0), nSequence=0)]
        coinbase_spending_tx.vout = [CTxOut(int(99.99 * COIN), destination_scriptpubkey_0)]
        coinbase_spending_tx.nLockTime = 0
        raw_coinbase_spending_tx_signed = self.nodes[0].signrawtransactionwithwallet(coinbase_spending_tx.serialize().hex())["hex"]

        # Node 0 accepts the transaction
        actual_tx_hash_hex = self.nodes[0].sendrawtransaction(raw_coinbase_spending_tx_signed)
        assert_equal(actual_tx_hash_hex, coinbase_spending_tx.rehash())
        self.sync_all(self.nodes[0:2])

        # Node 1 rejects the transaction
        node1_mempool_initial_size = self.nodes[1].getmempoolinfo()['size']
        node1_mempool_result_expected = [{'txid': coinbase_spending_tx.rehash(), 'allowed': False, 'reject-reason': 'txn-already-in-mempool'}]
        node1_mempool_result_actual = self.nodes[1].testmempoolaccept(rawtxs=[raw_coinbase_spending_tx_signed])
        for r in node1_mempool_result_actual:
            # we have no easy way of precomputing an expected value for wtxid.
            # It does not matter, because what we really want to check is that
            # txid is the one we are expecting. Thus, we can get rid of this
            # field.
            r.pop('wtxid')
        assert_equal(node1_mempool_result_expected, node1_mempool_result_actual)
        assert_equal(self.nodes[1].getmempoolinfo()['size'], node1_mempool_initial_size)  # Must not change mempool state


if __name__ == '__main__':
    SignetSignatureIndependentMerkleRootTest().main()
