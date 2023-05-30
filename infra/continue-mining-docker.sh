#!/usr/bin/env bash
#
# Itcoin
#
# This script is meant for debugging purposes. Assuming
# initialize-itcoin-docker.sh has been already executed once, restarts the
# continuous mining process from where it left off. The current datadir is
# reused: there is no need to delete it.
#
# Please note that you need to pass the BLOCKSCRIPT value via command line.
# You'll need to save it during the inizialization.
#
# The containers are run in host network mode, and thus the "--publish"
# arguments are not relevant. They are kept for documentation purposes, should
# we want to migrate to bridge networking mode.
#
# REQUIREMENTS:
# - docker
# - the itcoin docker image must be available and tagged
# - initialize-itcoin-docker.sh has been started and stopped already
#
# USAGE:
#     continue-mining-docker.sh <BLOCKSCRIPT>

set -eu

# https://stackoverflow.com/questions/59895/how-to-get-the-source-directory-of-a-bash-script-from-within-the-script-itself#246128
MYDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

# These should probably be taken from cmdline
ITCOIN_IMAGE_NAME="arthub.azurecr.io/itcoin-core"

# this uses the current checked out version. If you want to use a different
# version, you'll have to modify this variable, for now.
ITCOIN_IMAGE_TAG="git-"$("${MYDIR}"/compute-git-hash.sh)

CONTAINER_NAME="itcoin-node"
EXTERNAL_DATADIR="${MYDIR}/datadir"
INTERNAL_DATADIR="/opt/itcoin-core/datadir"

BITCOIN_PORT=38333
RPC_HOST=127.0.0.1 # localhost would fail if the system is ipv6-only
RPC_PORT=38332
ZMQ_PUBHASHTX_PORT=29009
ZMQ_PUBRAWBLOCK_PORT=29009
ZMQ_PUBITCOINBLOCK_PORT=29010

WALLET_NAME=itcoin_signer

errecho() {
    # prints to stderr
    >&2 echo "${@}"
}

cleanup() {
    # stop the itcoin daemon
    errecho "Itcoin daemon: cleaning up (deleting container ${CONTAINER_NAME})"
    docker stop "${CONTAINER_NAME}" > /dev/null
}

checkPrerequisites() {
    if ! command -v docker &> /dev/null; then
        errecho "Please install docker (https://www.docker.com/)"
        exit 1
    fi
    if ! command -v sort &> /dev/null; then
        errecho "The sort command is not available"
        exit 1
    fi
    if ! command -v uniq &> /dev/null; then
        errecho "The uniq command is not available"
        exit 1
    fi
}

# Automatically stop the container (wich will also self-remove at script exit
# or if an error occours
trap cleanup EXIT

# Do not run if the required packages are not installed
checkPrerequisites

# You will need to save the BLOCKSCRIPT value at first run in order to pass it here.
BLOCKSCRIPT=$1
shift

ITCOIN_IMAGE="${ITCOIN_IMAGE_NAME}:${ITCOIN_IMAGE_TAG}"
errecho "Using itcoin docker image ${ITCOIN_IMAGE}"

# The ZMQ topics do not need to be published on distinct ports. But Docker's
# "--publish" parameter fails if the same port is given multiple times.
# Thus we have to remove duplicates from the set of ZMQ_XXX_PORT variables.
declare -a ZMQ_PARAMS

# SC2046 shellcheck warning is:
#
#     done <<<$(printf '%s\n' "${ZMQ_PUBHASHTX_PORT}" "${ZMQ_PUBRAWBLOCK_PORT}" "${ZMQ_PUBITCOINBLOCK_PORT}" | sort | uniq )
#             ^-- SC2046 (warning): Quote this to prevent word splitting.
#
# But our goal is exactly generating multiple lines via the printf call via word
# splitting.
#
#shellcheck disable=SC2046
while IFS= read -r ZMQ_PORT; do
    ZMQ_PARAMS+=("--publish" "${ZMQ_PORT}:${ZMQ_PORT}")
done <<<$(printf '%s\n' "${ZMQ_PUBHASHTX_PORT}" "${ZMQ_PUBRAWBLOCK_PORT}" "${ZMQ_PUBITCOINBLOCK_PORT}" | sort | uniq )

# Start itcoin daemon
# Different from the wiki: the wallet is not automatically loaded now. It will
# instead be loaded afterwards, through the cli
docker run \
	--read-only \
	--name "${CONTAINER_NAME}" \
	--user "$(id --user):$(id --group)" \
	--detach \
	--rm \
	--env BITCOIN_PORT="${BITCOIN_PORT}" \
	--env BLOCKSCRIPT="${BLOCKSCRIPT}" \
	--env RPC_HOST="${RPC_HOST}" \
	--env RPC_PORT="${RPC_PORT}" \
	--env ZMQ_PUBHASHTX_PORT="${ZMQ_PUBHASHTX_PORT}" \
	--env ZMQ_PUBRAWBLOCK_PORT="${ZMQ_PUBRAWBLOCK_PORT}" \
	--env ZMQ_PUBITCOINBLOCK_PORT="${ZMQ_PUBITCOINBLOCK_PORT}" \
	--network=host \
	--publish "${BITCOIN_PORT}":"${BITCOIN_PORT}" \
	--publish "${RPC_PORT}":"${RPC_PORT}" \
	"${ZMQ_PARAMS[@]}" \
	--tmpfs /opt/itcoin-core/configdir \
	--mount type=bind,source="${EXTERNAL_DATADIR}",target="${INTERNAL_DATADIR}" \
	"${ITCOIN_IMAGE}" \
	bitcoind

# Open the wallet WALLET_NAME
errecho "Load wallet ${WALLET_NAME}"
"${MYDIR}/run-docker-bitcoin-cli.sh" loadwallet "${WALLET_NAME}" >/dev/null
errecho "Wallet ${WALLET_NAME} loaded"

# Retrieve the address of the first transaction in this blockchain
errecho "Retrieve the address of the first transaction we find"
ADDR=$("${MYDIR}/run-docker-bitcoin-cli.sh" listtransactions | docker run --rm --interactive "${ITCOIN_IMAGE}" jq --raw-output '.[0].address')
errecho "Address ${ADDR} retrieved"

# Let's start mining continuously. We'll reuse the same ADDR as before.
errecho "Keep mining eternally"
"${MYDIR}/run-docker-miner.sh" "${ADDR}" --ongoing
errecho "You should never reach here"
