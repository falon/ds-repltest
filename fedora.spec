{{ data.credit_line }}
{% from 'macros.spec' import dependencies, for_python_versions, underscored_or_pypi, macroed_url -%}
%global pypi_name {{ data.name }}
{%- if data.srcname %}
%global srcname {{ data.srcname }}
{%- endif %}

Name:           {{ data.pkg_name|macroed_pkg_name(data.srcname) }}
Version:        {{ data.version }}
Release:        1%{?dist}
Summary:        {{ data.summary }}

License:        {{ data.license }}
URL:            {{ data.home_page }}
Source0:        {{ data.source0|replace(data.name, '%{pypi_name}')|replace(data.version, '%{version}')|macroed_url }}

{%- if not data.has_extension %}
BuildArch:      noarch
{%- endif %}
{%- for pv in data.sorted_python_versions %}
{{ dependencies(data.build_deps, False, pv, data.base_python_version, False) }}
{%- endfor %}
%{?systemd_requires}
Requires(pre): /usr/sbin/useradd, /usr/bin/getent
Requires(postun): /usr/sbin/userdel


%description
{{ data.description|truncate(400)|wordwrap }}
{% for pv in data.sorted_python_versions %}
%package -n     {{data.pkg_name|macroed_pkg_name(data.srcname)|name_for_python_version(pv, True) }}
Summary:        %{summary}
%{?python_provide:%python_provide {{data.pkg_name|macroed_pkg_name(data.srcname)|name_for_python_version(pv, True)}}}
{{ dependencies(data.runtime_deps, True, pv, pv) }}
%description -n {{data.pkg_name|macroed_pkg_name(data.srcname)|name_for_python_version(pv, True) }}
{{ data.description|truncate(400)|wordwrap }}
{% endfor -%}
{%- if data.sphinx_dir %}
%package -n {{ data.pkg_name|macroed_pkg_name(data.srcname)|name_for_python_version(None, True) }}-doc
Summary:        {{ data.name }} documentation
%description -n {{ data.pkg_name|macroed_pkg_name(data.srcname)|name_for_python_version(None, True) }}-doc
Documentation for {{ data.name }}
{%- endif %}

%prep
%autosetup -n {{ data.dirname|replace(data.name, '%{pypi_name}')|replace(data.version, '%{version}')|default('%{pypi_name}-%{version}', true) }}
{%- if data.has_bundled_egg_info %}
# Remove bundled egg-info
rm -rf %{pypi_name}.egg-info
{%- endif %}

%build
{%- for pv in data.sorted_python_versions %}
%py{{ pv }}_build
{%- endfor %}
{%- if data.sphinx_dir %}
# generate html docs
PYTHONPATH=${PWD} {{ "sphinx-build"|script_name_for_python_version(data.base_python_version, False, True) }} {{ data.sphinx_dir }} html
# remove the sphinx-build leftovers
rm -rf html/.{doctrees,buildinfo}
{%- endif %}

%install
{%- if data.python_versions|length > 0 %}
# Must do the default python version install last because
# the scripts in /usr/bin are overwritten with every setup.py install.
{%- endif %}
{%- for pv in data.python_versions + [data.base_python_version] %}
{%- if pv == data.base_python_version and data.python_versions and data.scripts %}
rm -rf %{buildroot}%{_bindir}/*
{%- endif %}
%py{{ pv }}_install
mv %{buildroot}%{_sysconfdir}/%{pypi_name}/%{pypi_name}.conf.dist %{buildroot}%{_sysconfdir}/%{pypi_name}/%{pypi_name}.conf
install -d -Cm 0755 %{buildroot}%{_unitdir}
install -Cm 0644 %{buildroot}%{_unitdir}/*.service %{buildroot}%{_unitdir}
install -d -m 0644 %{buildroot}%{_localstatedir}/log/%{pypi_name}
install -d -m 0700 %{buildroot}%{_rundir}/%{pypi_name}
mv %{buildroot}%{_sysconfdir}/logrotate.d/%{pypi_name}.logrotate %{buildroot}%{_sysconfdir}/logrotate.d/%{pypi_name}
rm -rf %{buildroot}/%{python3_sitelib}/dsReplTest/etc %{buildroot}/%{python3_sitelib}/dsReplTest/systemd
{%- endfor -%}

{%- for pv in data.sorted_python_versions %}
%pre -n     {{data.pkg_name|macroed_pkg_name(data.srcname)|name_for_python_version(pv, True) }}
getent group dsrepl >/dev/null || groupadd -r dsrepl
getent passwd dsrepl >/dev/null || \
        useradd -r -g dsrepl -d /run/%{pypi_name} -M -s /sbin/nologin \
                -c "%{pypi_name}" dsrepl
exit 0

%post -n     {{data.pkg_name|macroed_pkg_name(data.srcname)|name_for_python_version(pv, True) }}
%systemd_post %{pypi_name}.service

%preun -n     {{data.pkg_name|macroed_pkg_name(data.srcname)|name_for_python_version(pv, True) }}
%systemd_preun %{pypi_name}.service

%postun -n     {{data.pkg_name|macroed_pkg_name(data.srcname)|name_for_python_version(pv, True) }}
%systemd_postun_with_restart %{pypi_name}.service
if [ "$1" -eq "0" ] ; then
  groupdel dsrepl 2> /dev/null; true
  userdel  dsrepl 2> /dev/null; true
fi
{%- endfor %}

%clean
rm -rf $RPM_BUILD_ROOT

{% if data.has_test_suite %}

%check
{%- for pv in data.sorted_python_versions %}
%{__python{{ pv }}} setup.py test
{%- endfor %}
{%- endif %}
{% for pv in data.sorted_python_versions %}
%files -n {{ data.pkg_name|macroed_pkg_name(data.srcname)|name_for_python_version(pv, True) }}
{%- if data.doc_license %}
%license %{_datarootdir}/licenses/%{pypi_name}/{{data.doc_license|join(' ')}}
{%- endif %}
{%- if data.doc_files %}
%doc %{_docdir}/%{pypi_name}/{{data.doc_files|join(' ') }}
{%- endif %}
%config(noreplace) %{_sysconfdir}/%{pypi_name}/%{pypi_name}.conf
%config(noreplace) %{_sysconfdir}/logrotate.d/%{pypi_name}
%dir %attr(0644,dsrepl,dsrepl) %{_localstatedir}/log/%{pypi_name}
%dir %attr(0700,dsrepl,dsrepl) %{_rundir}/%{pypi_name}
%attr(0644,root,root) %{_unitdir}/*.service
{%- if pv == data.base_python_version %}
{%- for script in data.scripts %}
%{_bindir}/{{ script }}
{%- endfor %}
{%- endif %}
{%- if data.py_modules %}
{%- for module in data.py_modules -%}
{%- if pv == '3' %}
%{python{{ pv }}_sitelib}/__pycache__/*
{%- endif %}
%{python{{ pv }}_sitelib}/{{ data.name | module_to_path(module) }}.py{% if pv != '3'%}*{% endif %}
{%- endfor %}
{%- endif %}
{%- if data.has_extension %}
{%- if data.has_packages %}
{%- for package in data.packages %}
%{python{{ pv }}_sitearch}/{{ package | package_to_path(data.name) }}
{%- endfor %}
{%- endif %}
{%- if data.has_pth %}
%{python{{ pv }}_sitearch}/{{ underscored_or_pypi(data.name, data.underscored_name) }}-%{version}-py%{python{{ pv }}_version}-*.pth
{%- endif %}
%{python{{ pv }}_sitearch}/{{ underscored_or_pypi(data.name, data.underscored_name) }}-%{version}-py%{python{{ pv }}_version}.egg-info
{%- else %}
{%- if data.has_packages %}
{%- for package in data.packages %}
%{python{{ pv }}_sitelib}/{{ package | package_to_path(data.name) }}
{%- endfor %}
{%- endif %}
{%- if data.has_pth %}
%{python{{ pv }}_sitelib}/{{ underscored_or_pypi(data.name, data.underscored_name) }}-%{version}-py%{python{{ pv }}_version}-*.pth
{%- endif %}
%{python{{ pv }}_sitelib}/{{ underscored_or_pypi(data.name, data.underscored_name) }}-%{version}-py%{python{{ pv }}_version}.egg-info
{%- endif %}
{% endfor %}
{%- if data.sphinx_dir %}
%files -n {{ data.pkg_name|macroed_pkg_name(data.srcname)|name_for_python_version(None, True) }}-doc
%doc html
{%- if data.doc_license %}
%license {{data.doc_license|join(' ')}}
{%- endif %}
{% endif %}

%changelog
* Tue Jan 12 2021 Marco F <m.faverof@gmail.com> - 1.0-1
- Initial package.
* {{ data.changelog_date_packager }} - {{ data.version }}-1
- Improved systemd management.
