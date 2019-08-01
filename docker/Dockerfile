FROM centos:7

RUN yum -y install git bzip2 gcc make openssl-devel readline-devel zlib-devel docker

RUN git clone https://github.com/rbenv/rbenv.git /root/.rbenv

RUN mkdir /root/.rbenv/plugins

RUN git clone https://github.com/rbenv/ruby-build.git /root/.rbenv/plugins/ruby-build

RUN echo 'export PATH="/root/.rbenv/shims:/root/.rbenv/plugins/ruby-build/bin:$PATH"' >> /root/.bashrc

RUN /root/.rbenv/bin/rbenv install 2.4.2

RUN /root/.rbenv/bin/rbenv global 2.4.2

RUN gem install bundle
