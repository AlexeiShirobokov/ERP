document.addEventListener('DOMContentLoaded', function () {
    const checkButton = document.getElementById('check-candidate-otipb-btn');
    const statusBlock = document.getElementById('candidate-otipb-status');

    if (!checkButton) {
        return;
    }

    const checkUrl = checkButton.dataset.url;

    function getField(name) {
        return document.querySelector(`[name="${name}"]`);
    }

    function setStatus(text, className) {
        if (!statusBlock) {
            return;
        }

        statusBlock.textContent = text || '';
        statusBlock.className = className || 'small mt-1 text-muted';
    }

    function setFieldValue(name, value) {
        const field = getField(name);

        if (!field) {
            return;
        }

        if (field.tagName === 'SELECT') {
            const optionExists = Array.from(field.options).some(function (option) {
                return option.value === String(value || '');
            });

            if (optionExists) {
                field.value = value || '';
            }

            return;
        }

        field.value = value || '';
    }

    function fillCandidateFields(data) {
        setFieldValue('hh_vacancy', data.hh_vacancy);
        setFieldValue('position', data.position);
        setFieldValue('contacts', data.contacts);
        setFieldValue('medical_commission', data.medical_commission);
        setFieldValue('comment', data.comment);
        setFieldValue('birth_year', data.birth_year);
        setFieldValue('qualification', data.qualification);
        setFieldValue('work_experience', data.work_experience);
        setFieldValue('note', data.note);
        setFieldValue('otipb', data.otipb);
        setFieldValue('refusal_reason', data.refusal_reason);
        setFieldValue('ticket', data.ticket);
        setFieldValue('stage', data.stage);
    }

    checkButton.addEventListener('click', function () {
        const fullNameField = getField('full_name');

        if (!fullNameField) {
            setStatus(
                'Поле ФИО не найдено на форме.',
                'small mt-1 text-danger'
            );
            return;
        }

        const fullName = fullNameField.value.trim();

        if (!fullName) {
            setStatus(
                'Сначала введите ФИО.',
                'small mt-1 text-warning'
            );
            return;
        }

        setStatus(
            'Проверяем кандидата...',
            'small mt-1 text-muted'
        );

        const url = `${checkUrl}?full_name=${encodeURIComponent(fullName)}`;

        fetch(url, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            },
        })
            .then(function (response) {
                return response.json();
            })
            .then(function (result) {
                if (!result.success) {
                    setStatus(
                        result.message || 'Ошибка проверки.',
                        'small mt-1 text-danger'
                    );
                    return;
                }

                if (!result.found) {
                    setFieldValue('otipb', '');

                    setStatus(
                        'Совпадений не найдено. Поле ОТИПБ очищено.',
                        'small mt-1 text-warning'
                    );

                    return;
                }

                const data = result.data || {};

                fillCandidateFields(data);

                setStatus(
                    `Кандидат найден. Подгружены последние данные от ${data.source_date || 'последней записи'}.`,
                    'small mt-1 text-success'
                );
            })
            .catch(function (error) {
                console.error(error);

                setStatus(
                    'Ошибка при проверке кандидата.',
                    'small mt-1 text-danger'
                );
            });
    });
});