FROM php:8.3-cli

# System deps
RUN apt-get update && apt-get install -y \
    libzip-dev unzip git \
    && docker-php-ext-install zip pdo_sqlite \
    && rm -rf /var/lib/apt/lists/*

# Install Composer
COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

# Install Xdebug
RUN pecl install xdebug && docker-php-ext-enable xdebug

# Configure Xdebug for remote debugging
RUN echo "xdebug.mode=debug,trace" >> /usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini \
    && echo "xdebug.start_with_request=trigger" >> /usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini \
    && echo "xdebug.client_host=xdebug-listener" >> /usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini \
    && echo "xdebug.client_port=9003" >> /usr/local/etc/php/conf.d/docker-php-ext-xdebug.ini

WORKDIR /app

COPY composer.json ./
RUN composer install --no-dev --no-interaction --prefer-dist

COPY . .

# Ensure SQLite database exists
RUN mkdir -p database && touch database/database.sqlite

ENV OTEL_PHP_AUTOLOAD_ENABLED=true
ENV OTEL_SERVICE_NAME=sample-php
ENV OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
ENV OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf

EXPOSE 8080

CMD ["php", "artisan", "serve", "--host=0.0.0.0", "--port=8080"]
