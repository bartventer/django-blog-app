from django.contrib.postgres import search
from django.core import paginator
from django.shortcuts import render, get_object_or_404
from .models import Post, Comment
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.views.generic import ListView
from .forms import EmailPostForm, CommentForm, SearchForm
from django.core.mail import send_mail
from taggit.models import Tag
from django.db.models import Count
from django.contrib.postgres.search import TrigramSimilarity
import os
from dotenv import load_dotenv
from mysite.settings import *
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)


def post_list(request, tag_slug=None):
    object_list = Post.published.all()
    tag = None

    if tag_slug:
        tag = get_object_or_404(Tag, slug=tag_slug)
        object_list = object_list.filter(tags__in=[tag])

    paginator = Paginator(object_list, per_page=3)
    page = request.GET.get('page')
    try:
        posts = paginator.page(page)
    except PageNotAnInteger:
        #If page is not an integer deliver the first page
        posts = paginator.page(1)
    except EmptyPage:
        #If page is out of range deliver last page of results
        posts = paginator.page(paginator.num_pages)
    return render(
        request,
        'blog/post/list.html',
        {'page':page,
        'posts':posts,
        'tag':tag,
        'home_page': True}
    )

def post_detail(request, year, month, day, post):
    post = get_object_or_404(
        Post,
        slug=post,
        status='published',
        publish__year=year,
        publish__month=month,
        publish__day=day
    )
    # List of active comments for this post
    comments = post.comments.filter(active=True)

    new_comment = None
    
    if request.method == 'POST':
        #A comment was posted
        comment_form = CommentForm(data=request.POST)
        #Comment form validation
        if comment_form.is_valid():
            # Create comment object, but don't save to database yet
            new_comment = comment_form.save(commit=False)
            # Assign the current post to the comment
            new_comment.post = post
            # Commit the change to the database
            new_comment.save()
    else:
        comment_form = CommentForm()
    
    # List of similar posts
    # Current post, list of tag ids
    post_tags_ids = post.tags.values_list('id', flat=True)
    # All posts containing ANY of these tags, excluding the current post
    similar_posts = Post.published.filter(tags__in=post_tags_ids).exclude(id=post.id)
    # Generate a calculated field that contains the number of tags shared with all tags queried
    similar_posts = similar_posts.annotate(same_tags=Count('tags')).order_by('-same_tags', '-publish')[:4]

    return render(
        request,
        'blog/post/detail.html',
        {'post':post,'comments':comments, 'new_comment':new_comment, 'comment_form':comment_form, 'similar_posts':similar_posts}
    )

class PostListView(ListView):
    queryset = Post.published.all()
    context_object_name = 'posts'
    paginate_by = 3
    template_name = 'blog/post/list.html'

def post_share(request, post_id):
    # Retrieve post by id
    post = get_object_or_404(Post, id=post_id, status='published')
    sent=False
    if request.method == 'POST':
        # Form was submitted
        form = EmailPostForm(request.POST)
        if form.is_valid():
            # Form fields passed validation
            cd = form.cleaned_data
            # Send email
            post_url = request.build_absolute_uri(post.get_absolute_url())
            subject = f"{cd['name']} recommends you read {post.title}"
            message = f'Read "{post.title}" at {post_url}\n\n{cd["name"]}\'s comments: {cd["comments"]}'
            send_mail(subject, message, os.getenv('EMAIL_HOST_USER'), [cd['to']])
            sent = True
    else:
        form = EmailPostForm()
    return render(request, 'blog/post/share.html', {'post':post, 'form':form, 'sent':sent})

def post_search(request):
    # no query submitted
    form = SearchForm()
    query = None
    results = []

    # query submitted
    if 'query' in request.GET:
        form = SearchForm(request.GET)
        #query validation
        if form.is_valid():
            query = form.cleaned_data['query']
            #Trigram Similarity - performing matches based on three consecutive chars matches
            results = Post.published.annotate(
                similarity=TrigramSimilarity('title',query),
            ).filter(similarity__gt=0.1).order_by('-similarity')

    return render (request, 'blog/post/search.html',{'form':form, 'query':query, 'results':results, 'search':True})
