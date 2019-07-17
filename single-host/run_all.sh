#!/bin/bash
set -e

CONFIG_DIR=$PWD/volumes/config-init/db
GLUU_VERSION=4.0.0_dev
DOMAIN=""
ADMIN_PW=""
EMAIL=""
ORG_NAME=""
COUNTRY_CODE=""
STATE=""
CITY=""
DOCKER_COMPOSE=${DOCKER_COMPOSE:-docker-compose}
DOCKER=${DOCKER:-docker}

# @TODO: remove this function when we have .zip/.tar.gz for distribution
get_files(){
    has_gcp=$(cat gcp_kms_creds.json|wc -l)

    # we're in test-drive
    if [ "$has_gcp" = "0" ]; then
        folder="test-drive"
    else
        folder="examples"
    fi

    if [ ! -f docker-compose.yml ]; then
        wget -q https://raw.githubusercontent.com/GluuFederation/gluu-docker/4.0.0/$folder/single-host/docker-compose.yml -O ./docker-compose.yml
    fi
    if [ ! -f vault_gluu_policy.hcl ]; then
        wget -q https://raw.githubusercontent.com/GluuFederation/gluu-docker/4.0.0/$folder/single-host/vault_gluu_policy.hcl -O ./vault_gluu_policy.hcl
    fi
}

mask_password(){
    password=''
    while IFS= read -r -s -n1 char; do
      [[ -z $char ]] && { printf '\n'; break; }
      if [[ $char == $'\b' ]]; then
          [[ -n $password ]] && password=${password%?}
          printf '\b \b'
      else
        password+=$char
        printf '*'
      fi
done
}

check_health(){
    echo -n "[I] Launching "
    timeout="10 minute"
    endtime=$(date -ud "$timeout" +%s)
    while [[ $(date -u +%s) -le $endtime ]]; do
        nginx_ip=$($DOCKER inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' nginx)
        status_code=$(timeout 5s curl -o /dev/null --silent -k --head --write-out '%{http_code}\n' https://"$nginx_ip" || true)
        if [ "$status_code" -eq "302" ] &>/dev/null
        then
                printf "\n[I] Gluu Server installed successfully; please visit https://%s\n" "$DOMAIN"
                break
        fi
        sleep 5
        echo -n "."
    done
}

gather_ip() {
    echo "[I] Determining OS Type and Attempting to Gather External IP Address"
    unameOut="$(uname -s)"
    case "${unameOut}" in
        Linux*)     machine=Linux;;
        Darwin*)    machine=Mac;;
        *)          machine="UNKNOWN:${unameOut}"
    esac
    echo "Host is detected as ${machine}"

    if [[ $machine == Linux ]]; then
        HOST_IP=$(ip route get 8.8.8.8 | awk -F"src " 'NR==1{split($2,a," ");print a[1]}')
    elif [[ $machine == Mac ]]; then
        HOST_IP=$(route get default | grep gateway | awk '{print $2}')
    else
        echo "Cannot determine IP address."
        read -rp "Please input the hosts external IP Address: " HOST_IP
    fi
}

valid_ip() {
    local  ip=$1
    local  stat=1

    if [[ $ip =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
        OIFS=$IFS
        IFS='.'
        ip=("$ip")
        IFS=$OIFS
        [[ ${ip[0]} -le 255 && ${ip[1]} -le 255 \
            && ${ip[2]} -le 255 && ${ip[3]} -le 255 ]]
        stat=$?
    fi
    return $stat
}

confirm_ip() {
    read -rp "Is this the correct external IP Address: ${HOST_IP} [Y/n]? " cont
    case "$cont" in
        y|Y)
            return 0
            ;;
        n|N)
            read -rp "Please input the hosts external IP Address: " HOST_IP
            if valid_ip "$HOST_IP"; then
                return 0
            else
                echo "Please enter a valid IP Address."
                gather_ip
                return 1
            fi
            return 0
            ;;
        *)
            return 0
            ;;
    esac
}

check_docker() {
    if [ -z "$(command -v "$DOCKER")" ]; then
        echo "[E] Unable to detect docker executable"
        echo "[W] Make sure docker is installed and available in PATH or explictly passed as DOCKER environment variable"
        exit 1
    fi
}

check_docker_compose() {
    if [ -z "$(command -v "$DOCKER_COMPOSE")" ]; then
        echo "[E] Unable to detect docker-compose executable"
        echo "[W] Make sure docker-compose is installed and available in PATH or explictly passed as DOCKER_COMPOSE environment variable"
        exit 1
    fi
}

load_services() {
    echo "[I] Deploying containers"
    DOMAIN=$DOMAIN HOST_IP=$HOST_IP $DOCKER_COMPOSE up -d
}

prepare_config_secret() {
    echo "[I] Preparing cluster-wide config and secret"

    if [[ -z $($DOCKER ps --filter name=consul -q) ]]; then
        $DOCKER_COMPOSE up -d consul
    fi

    if [[ -z $($DOCKER ps --filter name=vault -q) ]]; then
        $DOCKER_COMPOSE up -d vault
        setup_vault
    fi

    echo "[I] Checking existing config in Consul"
    retry=1
    while [[ $retry -le 3 ]]; do
        sleep 5
        consul_ip=$($DOCKER inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' consul)
        DOMAIN=$(curl "$consul_ip":8500/v1/kv/gluu/config/hostname?raw -s)

        if [[ $DOMAIN != "" ]]; then
            break
        fi

        echo "[W] Unable to get config in Consul; retrying ..."

        retry=$((retry+1))
        sleep 5
    done
    # if there's no config in Consul, check from previously saved config
    if [[ -z $DOMAIN ]]; then
        echo "[W] Configuration not found in Consul"

         if [[ -f $CONFIG_DIR/config.json  ]]; then
            read -rp "[I] Load previously saved configuration in local disk? [Y/n]" load_choice

            if [[ $load_choice != "n" && $load_choice != "N" ]]; then
                DOMAIN=$(cat "$CONFIG_DIR"/config.json |  awk ' /'hostname'/ {print $2} ' | sed 's/[",]//g')

                if [[ ! -z "$DOMAIN" ]]; then
                    $DOCKER run \
                        --rm \
                        --network container:consul \
                        -v "$CONFIG_DIR":/opt/config-init/db/ \
                        -v "$PWD"/vault_role_id.txt:/etc/certs/vault_role_id \
                        -v "$PWD"/vault_secret_id.txt:/etc/certs/vault_secret_id \
                        -e GLUU_CONFIG_CONSUL_HOST=consul \
                        -e GLUU_SECRET_VAULT_HOST=vault \
                        gluufederation/config-init:$GLUU_VERSION load
                fi
            fi
        fi
    fi

    # config is not loaded from previously saved configuration
    if [[ -z $DOMAIN ]]; then
        if [[ ! -f "$PWD/generate.json" ]]; then
            echo "[I] Creating new configuration, please input the following parameters"
            read -rp "Enter Hostname (demoexample.gluu.org):                 " DOMAIN
            if ! [[ $DOMAIN == *"."*"."* ]]; then
                echo "[E] Hostname provided is invalid. Please enter a FQDN with the format demoexample.gluu.org"
                exit 1
            fi
            read -rp "Enter Country Code:           " COUNTRY_CODE
            read -rp "Enter State:                  " STATE
            read -rp "Enter City:                   " CITY
            read -rp "Enter Email:                  " EMAIL
            read -rp "Enter Organization:           " ORG_NAME
            while true; do
                echo "Enter Admin/LDAP Password:"
                mask_password
                ADMIN_PW=$password
                echo "Confirm Admin/LDAP Password:"
                mask_password
                password2=$password
                [ "$ADMIN_PW" = "$password2" ] && break || echo "Please try again"
            done

            case "$ADMIN_PW" in
                * ) ;;
                "") echo "Password cannot be empty"; exit 1;
            esac

            read -rp "Continue with the above settings? [Y/n]" choiceCont

            case "$choiceCont" in
                y|Y ) ;;
                n|N ) exit 1 ;;
                * )   ;;
            esac

            cat > generate.json <<EOL
{
    "hostname": "$DOMAIN",
    "country_code": "$COUNTRY_CODE",
    "state": "$STATE",
    "city": "$CITY",
    "admin_pw": "$ADMIN_PW",
    "email": "$EMAIL",
    "org_name": "$ORG_NAME"
}
EOL
        fi

        # mount generate.json to mark for new config and secret
        $DOCKER run \
            --rm \
            --network container:consul \
            -v "$CONFIG_DIR":/opt/config-init/db/ \
            -v "$PWD"/vault_role_id.txt:/etc/certs/vault_role_id \
            -v "$PWD"/vault_secret_id.txt:/etc/certs/vault_secret_id \
            -v "$PWD"/generate.json:/opt/config-init/db/generate.json \
            -e GLUU_CONFIG_CONSUL_HOST=consul \
            -e GLUU_SECRET_VAULT_HOST=vault \
            gluufederation/config-init:$GLUU_VERSION load
        rm generate.json
    fi
}

### unsealing the vault
init_vault() {
    vault_initialized=$($DOCKER exec vault vault status -format=yaml | grep initialized | awk -F ': ' '{print $2}')

    if [ "${vault_initialized}" = "true" ]; then
        echo "[I] Vault already initialized"
    else
        echo "[W] Vault is not initialized; trying to initialize Vault with 1 recovery key and root token"
        $DOCKER exec vault vault operator init \
            -key-shares=1 \
            -key-threshold=1 \
            -recovery-shares=1 \
            -recovery-threshold=1 > "$PWD"/vault_key_token.txt
        echo "[I] Vault recovery key and root token saved to $PWD/vault_key_token.txt"
    fi
}

get_root_token() {
    if [ -f "$PWD"/vault_key_token.txt ]; then
        cat "$PWD"/vault_key_token.txt | grep "Initial Root Token" | awk -F ': ' '{print $2}'
    fi
}

enable_approle() {
    $DOCKER exec vault vault login -no-print "$(get_root_token)"

    approle_enabled=$($DOCKER exec vault vault auth list | grep 'approle' || :)

    if [ -z "${approle_enabled}" ]; then
        echo "[W] AppRole is not enabled; trying to enable AppRole"
        $DOCKER exec vault vault auth enable approle
        $DOCKER exec vault vault write auth/approle/role/gluu policies=gluu
        $DOCKER exec vault \
            vault write auth/approle/role/gluu \
                secret_id_ttl=0 \
                token_num_uses=0 \
                token_ttl=20m \
                token_max_ttl=30m \
                secret_id_num_uses=0

        $DOCKER exec vault \
            vault read -field=role_id auth/approle/role/gluu/role-id > vault_role_id.txt

        $DOCKER exec vault \
            vault write -f -field=secret_id auth/approle/role/gluu/secret-id > vault_secret_id.txt
    else
        echo "[I] AppRole already enabled"
    fi
}

write_policy() {
    $DOCKER exec vault vault login -no-print "$(get_root_token)"

    policy_created=$($DOCKER exec vault vault policy list | grep gluu || :)

    if [ -z "${policy_created}" ]; then
        echo "[W] Gluu policy is not created; trying to create one"
        $DOCKER exec vault vault policy write gluu /vault/config/policy.hcl
    else
        echo "[I] Gluu policy already created"
    fi
}

get_unseal_key() {
    if [ -f "$PWD"/vault_key_token.txt ]; then
        cat "$PWD"/vault_key_token.txt | grep "Unseal Key 1" | awk -F ': ' '{print $2}'
    fi
}

unseal_vault() {
    vault_sealed=$($DOCKER exec vault vault status -format yaml | grep 'sealed' | awk -F ' ' '{print $2}' || :)
    if [ "${vault_sealed}" = "false" ]; then
        echo "[I] Vault already unsealed"
    else
        has_gcp=$(cat gcp_kms_creds.json|wc -l)
        if [ "$has_gcp" = "0" ]; then
            echo "[I] Unsealing Vault manually"
            $DOCKER exec vault vault operator unseal "$(get_unseal_key)"
        fi
    fi
}

setup_vault() {
    echo "[I] Checking seal status in Vault"
    retry=1

    while [[ $retry -le 3 ]]; do
        sleep 5
        vault_id=$($DOCKER ps -q --filter name=vault)
        if [ ! -z "$vault_id" ]; then
            vault_status=$($DOCKER exec vault vault status -format yaml | grep 'sealed' | awk -F ': ' '{print $2}')
            if [ ! -z "$vault_status" ]; then
                break
            fi
        fi

        echo "[W] Unable to get seal status in Vault; retrying ..."
        retry=$((retry+1))
        sleep 5
    done

    init_vault
    sleep 5
    unseal_vault
    sleep 5
    write_policy
    enable_approle
}

# ==========
# entrypoint
# ==========
check_docker
check_docker_compose

mkdir -p "$CONFIG_DIR"
touch vault_role_id.txt
touch vault_secret_id.txt
touch gcp_kms_stanza.hcl
touch gcp_kms_creds.json
touch couchbase_chain.pem
touch couchbase_pkey.key

get_files

gather_ip
until confirm_ip; do : ; done

prepare_config_secret
load_services
check_health