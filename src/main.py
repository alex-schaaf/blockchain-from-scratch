import hashlib
from time import time
from uuid import uuid4
from typing import Optional
from urllib.parse import urlparse

from fastapi import FastAPI, status
from pydantic import BaseModel
import requests
from starlette.status import HTTP_201_CREATED


class Transaction(BaseModel):
    sender: str
    recipient: str
    amount: int


class Block(BaseModel):
    index: int
    timestamp: float
    transactions: list[Transaction]
    proof: int
    previous_hash: str


class Blockchain:
    def __init__(self):
        self.chain: list[Block] = []
        self.current_transactions: list[Transaction] = []
        self.nodes: set[str] = set()

        # create genesis block
        self.new_block(previous_hash=1, proof=100)

    def new_block(self, proof: int, previous_hash: Optional[str] = None) -> Block:
        """Generate new Block in the Blockchain

        Parameters
        ----------
        proof : int
            Proof given by proof-of-work algorithm
        previous_hash : str, optional
            Hash of previous Block, by default None

        Returns
        -------
        Block
            The new Block
        """
        block = Block(
            index=len(self.chain) + 1,
            timestamp=time(),
            transactions=self.current_transactions,
            proof=proof,
            previous_hash=previous_hash or self.hash(self.chain[-1]),
        )
        # reset current list of transactions
        self.current_transactions = []

        self.chain.append(block)
        return block

    def new_transaction(self, transaction: Transaction) -> int:
        """Creates a new transaction which goes into the next Block.

        Parameters
        ----------
        transaction : Transaction

        Returns
        -------
        int
            The index of the Block that will hold this transaction.
        """
        self.current_transactions.append(transaction)
        return self.last_block.index + 1

    @staticmethod
    def hash(block: Block) -> str:
        """Creates SHA-256 hash of given Block"""
        return hashlib.sha256(block.json().encode()).hexdigest()

    @property
    def last_block(self) -> Block:
        # returns last block from chain
        return self.chain[-1]

    @classmethod
    def proof_of_work(cls, last_proof: int) -> int:
        """Basic proof of work algorithm

        - Find a number p' such that hash (pp') contains leading 4 zeros, where
          p is the previous p' (last proof)
        """
        proof = 0
        while not cls.valid_proof(last_proof, proof):
            proof += 1
        return proof

    @staticmethod
    def valid_proof(last_proof: int, proof: int) -> bool:
        """Validate the proof by checking if hash(last_proof, proof)
        contains 4 leading zeros."""
        guess = f"{last_proof}{proof}".encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"

    def register_node(self, address: str):
        """Add a new node node to the list of nodes"""
        parsed_url = urlparse(address)
        self.nodes.add(parsed_url.netloc)

    def valid_chain(self, chain: set[str]) -> bool:
        """Determine if given blockchain is valid"""
        previous_block = chain[0]
        index = 1

        while index < len(chain):
            block = chain[index]

            if block.previous_hash != self.hash(previous_block):
                return False

            if not self.valid_proof(previous_block.proof, block.proof):
                return False

            previous_block = block
            index += 1

        return True

    def resolve_conflicts(self) -> bool:
        """Concesus Algorithm

        It resolves conflicts by replacing our chain with the longest one in the network.
        Returns True if your chain was replaces, otherwise False
        """
        neighbours = self.nodes
        new_chain = None

        max_length = len(self.chain)

        for node in neighbours:
            response = requests.get(f"http://{node}/chain")
            if response.status_code == 200:
                chain = response.json()["chain"]
                length = response.json()["length"]

                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain

        if new_chain:
            self.chain = new_chain
            return True
        return False


app = FastAPI(title="Blockchain")

# generate globally unique address for this node
node_id = str(uuid4()).replace("-", "")

blockchain = Blockchain()


@app.get("/mine")
def mine() -> Block:
    last_block = blockchain.last_block
    proof = blockchain.proof_of_work(last_block.proof)

    # the miner receives a reward for finding the proof
    blockchain.new_transaction(Transaction(sender="0", recipient=node_id, amount=1))

    # forge new block
    previous_hash = blockchain.hash(last_block)
    block = blockchain.new_block(proof, previous_hash)
    return block


@app.post("/transactions")
def new_transaction(transaction: Transaction):
    index = blockchain.new_transaction(transaction)
    return {"message": f"Transaction will be added to Block {index}"}


@app.get("/chain")
def get_full_chain():
    return {"chain": blockchain.chain, "length": len(blockchain.chain)}


@app.post("/nodes/", status_code=status.HTTP_201_CREATED)
def register_new_nodes(nodes: set[str]):
    for node in nodes:
        blockchain.register_node(node)

    return {"message": f"{len(nodes)} nodes have been added"}


@app.get("/nodes/resolve")
def consesus():
    replaced = blockchain.resolve_conflicts()

    if replaced:
        return {"message": "Your chain was replaced"}
    return {"message": "Your chain is authoritative"}
