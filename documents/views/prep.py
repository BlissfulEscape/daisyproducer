# This Python file uses the following encoding: utf-8
from daisyproducer.documents.models import Document
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.core.urlresolvers import reverse
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
import codecs
import re
from django import forms
from django.forms.formsets import formset_factory

class WordForm(forms.Form):
    word = forms.CharField(widget=forms.TextInput(attrs={'readonly':'readonly'}))
    detailed_accent = forms.BooleanField(required=False)

@login_required
def markup_accents(request, document_id):
    document = get_object_or_404(Document, pk=document_id)
    WordFormSet = formset_factory(WordForm, extra=0)

    if request.method == 'POST':
        formset = WordFormSet(request.POST)
        if formset.is_valid():
            for form in formset.forms:
                if form.cleaned_data['detailed_accent']:
                    # wrap the word in a span class and eventually
                    # create a new version with the modified content
                    print form.cleaned_data
            return HttpResponseRedirect(reverse('todo_detail', args=[document_id]))

    fileObj = codecs.open(document.latest_version().content.path, "r", "utf-8" )
    content = fileObj.read()
    fileObj.close()
    
    pattern = re.compile(u"\W+", re.UNICODE)
    words = pattern.split(content)
    unique_words = {}
    for word in words:
        unique_words[word] = None
    regex = re.compile(
        u"[àèìòùỳẁȁȅȉȍȕáéíóúýẃőűâêîôûŷŵäëïöüÿẅãẽĩõũỹąęįǫųāēīōūȳăĕĭŏŭǎěǐǒǔȧėȯẏẇạẹịọụỵẉḛḭṵṳøåæ]", 
        re.IGNORECASE)
    accented_words = [word for word in unique_words.keys() if regex.search(word)]
    initial= [{'word': word, 'detailed_accent': False} for word in accented_words]
    formset = WordFormSet(initial=initial)

    return render_to_response('documents/todo_prep.html', locals(),
                              context_instance=RequestContext(request))

